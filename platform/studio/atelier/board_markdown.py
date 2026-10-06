"""One safe renderer shared by stored messages and composer previews."""
import re
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

# A bare web address in running text. Trailing punctuation belongs to the sentence, not the address.
BARE_URL = re.compile(r'https?://[^\s<>"`]+')
TRAILING = '.,;:!?\'"'


def bare_url(match_text):
    url = match_text.rstrip(TRAILING)
    while url.endswith(')') and url.count(')') > url.count('('):
        url = url[:-1].rstrip(TRAILING)
    return url


def label(url):
    """A short, readable name for a bare address: its host and path, the middle elided when long."""
    parts = urlsplit(url)
    text = parts.netloc.removeprefix('www.') + parts.path.rstrip('/')
    if len(text) > 44:
        host, _, path = text.partition('/')
        tail = path.rsplit('/', 1)[-1]
        text = f'{host}/…/{tail[:18]}{"…" if len(tail) > 18 else ""}' if path else text[:43] + '…'
    return text


def render(body):
    parser = MarkdownIt('js-default', {'html': False, 'breaks': True, 'linkify': False})
    parser.disable('image')
    def valid_link(url):
        try:
            parsed = urlsplit(url)
            return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
        except ValueError:
            return False

    parser.validateLink = valid_link

    def alignment(state):
        for token in state.tokens:
            style = token.attrs.pop('style', None)
            if style in ('text-align:left', 'text-align:right', 'text-align:center'):
                token.attrSet('class', 'align-' + style.split(':')[1])

    parser.core.ruler.after('inline', 'table_alignment_classes', alignment)

    def linkify(state):
        """Turn bare web addresses into links named by host and path, outside code and existing links."""
        for block in state.tokens:
            if block.type != 'inline' or not block.children:
                continue
            children, depth = [], 0
            for token in block.children:
                if token.type in ('link_open', 'link_close'):
                    depth += 1 if token.type == 'link_open' else -1
                if token.type != 'text' or depth or 'http' not in token.content:
                    children.append(token)
                    continue
                last = 0
                for match in BARE_URL.finditer(token.content):
                    url = bare_url(match.group())
                    if not valid_link(url):
                        continue
                    if match.start() > last:
                        children.append(Token('text', '', 0, content=token.content[last:match.start()]))
                    opening = Token('link_open', 'a', 1, attrs={'href': url, 'class': 'url', 'title': url})
                    children += [opening, Token('text', '', 0, content=label(url)), Token('link_close', 'a', -1)]
                    last = match.start() + len(url)
                if last < len(token.content):
                    children.append(Token('text', '', 0, content=token.content[last:]))
            block.children = children

    parser.core.ruler.after('inline', 'bare_links', linkify)

    def link_open(renderer, tokens, index, options, env):
        tokens[index].attrSet('target', '_blank')
        tokens[index].attrSet('rel', 'noopener noreferrer')
        return renderer.renderToken(tokens, index, options, env)

    parser.add_render_rule('link_open', link_open)
    return parser.render(body)
