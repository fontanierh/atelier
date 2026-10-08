//! One safe renderer shared by stored messages, composer previews and attached documents: CommonMark with tables and
//! strikethrough, no raw HTML, no images, links only to http(s) addresses, and bare addresses made into short links.
use std::collections::HashMap;
use std::sync::{LazyLock, Mutex};

use markdown_it::parser::inline::Text;
use markdown_it::parser::linkfmt::LinkFormatter;
use markdown_it::plugins::cmark::inline::autolink::Autolink;
use markdown_it::plugins::cmark::inline::backticks::CodeInline;
use markdown_it::plugins::cmark::inline::link::Link;
use markdown_it::plugins::cmark::inline::newline::Softbreak;
use markdown_it::plugins::cmark::{block, inline};
use markdown_it::{MarkdownIt, Node, NodeValue, Renderer};
use regex::Regex;

/// A bare web address in running text. Trailing punctuation belongs to the sentence, not the address.
static BARE_URL: LazyLock<Regex> = LazyLock::new(|| Regex::new(r#"https?://[^\s<>"`]+"#).unwrap());
const TRAILING: &[char] = &['.', ',', ';', ':', '!', '?', '\'', '"'];

static PARSER: LazyLock<MarkdownIt> = LazyLock::new(|| {
    let mut md = MarkdownIt::new();
    md.link_formatter = Box::new(WebLinks);
    // CommonMark without images, which would load from anywhere.
    inline::newline::add(&mut md);
    inline::escape::add(&mut md);
    inline::backticks::add(&mut md);
    inline::emphasis::add(&mut md);
    inline::link::add(&mut md);
    inline::autolink::add(&mut md);
    inline::entity::add(&mut md);
    block::code::add(&mut md);
    block::fence::add(&mut md);
    block::blockquote::add(&mut md);
    block::hr::add(&mut md);
    block::list::add(&mut md);
    block::reference::add(&mut md);
    block::heading::add(&mut md);
    block::lheading::add(&mut md);
    block::paragraph::add(&mut md);
    markdown_it::plugins::extra::tables::add(&mut md);
    markdown_it::plugins::extra::strikethrough::add(&mut md);
    md
});

/// The parts of an address that matter here, split the way Python's urlsplit does.
pub struct Split<'a> {
    pub scheme: String,
    pub netloc: &'a str,
    pub path: &'a str,
}

/// None where urlsplit would raise (an unbalanced IPv6 bracket in the host).
pub fn urlsplit(url: &str) -> Option<Split<'_>> {
    let mut scheme = String::new();
    let mut rest = url;
    if let Some(colon) = url.find(':') {
        let candidate = &url[..colon];
        if !candidate.is_empty()
            && candidate.starts_with(|c: char| c.is_ascii_alphabetic())
            && candidate.chars().all(|c| c.is_ascii_alphanumeric() || "+-.".contains(c))
        {
            scheme = candidate.to_ascii_lowercase();
            rest = &url[colon + 1..];
        }
    }
    let mut netloc = "";
    if let Some(after) = rest.strip_prefix("//") {
        let end = after.find(['/', '?', '#']).unwrap_or(after.len());
        netloc = &after[..end];
        rest = &after[end..];
        if netloc.contains('[') != netloc.contains(']') {
            return None;
        }
    }
    let end = rest.find(['?', '#']).unwrap_or(rest.len());
    Some(Split { scheme, netloc, path: &rest[..end] })
}

pub fn valid_link(url: &str) -> bool {
    urlsplit(url).is_some_and(|parts| (parts.scheme == "http" || parts.scheme == "https") && !parts.netloc.is_empty())
}

#[derive(Debug)]
struct WebLinks;

impl LinkFormatter for WebLinks {
    fn validate_link(&self, url: &str) -> Option<()> {
        valid_link(url).then_some(())
    }

    fn normalize_link(&self, url: &str) -> String {
        markdown_it::parser::linkfmt::MDLinkFormatter::new().normalize_link(url)
    }

    fn normalize_link_text(&self, url: &str) -> String {
        url.to_owned()
    }
}

fn bare_url(found: &str) -> &str {
    let mut url = found.trim_end_matches(TRAILING);
    while url.ends_with(')') && url.matches(')').count() > url.matches('(').count() {
        url = url[..url.len() - 1].trim_end_matches(TRAILING);
    }
    url
}

/// A short, readable name for a bare address: its host and path, the middle elided when long.
pub fn label(url: &str) -> String {
    let parts = urlsplit(url).expect("labels are only made for valid links");
    let netloc = parts.netloc.strip_prefix("www.").unwrap_or(parts.netloc);
    let text = format!("{netloc}{}", parts.path.trim_end_matches('/'));
    if text.chars().count() <= 44 {
        return text;
    }
    match text.split_once('/') {
        Some((host, path)) if !path.is_empty() => {
            let tail = path.rsplit('/').next().unwrap_or("");
            let short: String = tail.chars().take(18).collect();
            format!("{host}/…/{short}{}", if tail.chars().count() > 18 { "…" } else { "" })
        }
        _ => text.chars().take(43).collect::<String>() + "…",
    }
}

/// A link that opens in a new tab and never tells the page it came from the board.
#[derive(Debug)]
struct WebLink {
    href: String,
    title: Option<String>,
    bare: bool,
}

impl NodeValue for WebLink {
    fn render(&self, node: &Node, fmt: &mut dyn Renderer) {
        let mut attrs = vec![("href", self.href.clone())];
        if self.bare {
            attrs.push(("class", "url".into()));
        }
        if let Some(title) = &self.title {
            attrs.push(("title", title.clone()));
        }
        attrs.push(("target", "_blank".into()));
        attrs.push(("rel", "noopener noreferrer".into()));
        fmt.open("a", &attrs);
        fmt.contents(&node.children);
        fmt.close("a");
    }
}

/// Lines break where the writer broke them, as in a chat.
#[derive(Debug)]
struct Break;

impl NodeValue for Break {
    fn render(&self, _: &Node, fmt: &mut dyn Renderer) {
        fmt.self_close("br", &[]);
        fmt.cr();
    }
}

fn text(content: &str) -> Node {
    Node::new(Text { content: content.to_owned() })
}

fn rewrite(node: &mut Node, in_link: bool) {
    let children = std::mem::take(&mut node.children);
    for mut child in children {
        if child.is::<Softbreak>() {
            node.children.push(Node::new(Break));
            continue;
        }
        if let Some(link) = child.cast::<Link>() {
            let value = WebLink { href: link.url.clone(), title: link.title.clone(), bare: false };
            child.replace(value);
        } else if let Some(link) = child.cast::<Autolink>() {
            let value = WebLink { href: link.url.clone(), title: None, bare: false };
            child.replace(value);
        }
        let linked = in_link || child.is::<WebLink>();
        if child.is::<CodeInline>() {
            node.children.push(child);
            continue;
        }
        if let (false, Some(found)) = (linked, child.cast::<Text>()) {
            let content = found.content.clone();
            if content.contains("http") {
                linkify(&content, &mut node.children);
                continue;
            }
        }
        rewrite(&mut child, linked);
        node.children.push(child);
    }
}

/// Bare web addresses become links named by host and path.
fn linkify(content: &str, out: &mut Vec<Node>) {
    let mut last = 0;
    for found in BARE_URL.find_iter(content) {
        let url = bare_url(found.as_str());
        if !valid_link(url) {
            continue;
        }
        if found.start() > last {
            out.push(text(&content[last..found.start()]));
        }
        let mut link = Node::new(WebLink { href: url.to_owned(), title: Some(url.to_owned()), bare: true });
        link.children.push(text(&label(url)));
        out.push(link);
        last = found.start() + url.len();
    }
    if last < content.len() {
        out.push(text(&content[last..]));
    }
}

pub fn render(body: &str) -> String {
    let mut root = PARSER.parse(body);
    rewrite(&mut root, false);
    // Raw HTML is off, so these attributes can only come from a table's alignment row.
    root.render()
        .replace(" style=\"text-align:left\"", " class=\"align-left\"")
        .replace(" style=\"text-align:right\"", " class=\"align-right\"")
        .replace(" style=\"text-align:center\"", " class=\"align-center\"")
}

static CACHE: LazyLock<Mutex<HashMap<String, String>>> = LazyLock::new(Default::default);

/// render, remembered: the board polls the same messages every few seconds.
pub fn cached(body: &str) -> String {
    if let Some(html) = CACHE.lock().unwrap().get(body) {
        return html.clone();
    }
    let html = render(body);
    let mut cache = CACHE.lock().unwrap();
    if cache.len() >= 4096 {
        cache.clear();
    }
    cache.insert(body.to_owned(), html.clone());
    html
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plain_paragraph() {
        assert_eq!(render("On it."), "<p>On it.</p>\n");
    }

    #[test]
    fn bare_addresses_become_safe_readable_links() {
        let html = render(
            "Report: https://claude.ai/artifact/U72bM2LBs3oQRADZXpnmAf. See (https://github.com/o/r/pull/85) \
             and `https://in.code/x` or [docs](https://example.com/guide) javascript:alert(1)",
        );
        assert!(html.contains(r#"<a href="https://claude.ai/artifact/U72bM2LBs3oQRADZXpnmAf" class="url""#), "{html}");
        assert!(html.contains(">claude.ai/artifact/U72bM2LBs3oQRADZXpnmAf</a>."));
        assert!(html.contains(r#"href="https://github.com/o/r/pull/85""#) && html.contains("85</a>)"));
        assert!(html.contains("<code>https://in.code/x</code>"));
        assert_eq!(html.matches(r#"href="https://example.com/guide""#).count(), 1);
        assert!(!html.contains(r#"href="javascript"#));
        let long = render("https://example.com/a/very/long/path/that/goes/on/and/on/to/the/final-segment-name");
        assert!(long.contains(">example.com/…/final-segment-name</a>"), "{long}");
    }
}
