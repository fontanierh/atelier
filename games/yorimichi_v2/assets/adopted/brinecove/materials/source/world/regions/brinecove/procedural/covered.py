"""One Brinecove constructor or shared geometry primitive; no sibling generation."""



def covered(rect, xa, xb, ya, yb):
    """Whether the rectangle [xa, xb] x [ya, yb] lies wholly inside rect (x0, x1, y0, y1)."""
    return rect is not None and rect[0] <= xa and xb <= rect[1] and rect[2] <= ya and yb <= rect[3]
