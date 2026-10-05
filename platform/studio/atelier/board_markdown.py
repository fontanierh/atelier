"""One safe renderer shared by stored messages and composer previews."""
from urllib.parse import urlsplit

from markdown_it import MarkdownIt


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

    def link_open(renderer, tokens, index, options, env):
        tokens[index].attrSet('target', '_blank')
        tokens[index].attrSet('rel', 'noopener noreferrer')
        return renderer.renderToken(tokens, index, options, env)

    parser.add_render_rule('link_open', link_open)
    return parser.render(body)
