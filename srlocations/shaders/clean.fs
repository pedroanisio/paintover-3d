// Fills hairline cracks in an ID pass before it is inked: a thin line of one colour between two sides that agree.
uniform float pixelsX; // = 1280
uniform float pixelsY; // = 720

vec4 effect(vec2 uv) {
    vec2 pixel = 1.0 / vec2(pixelsX, pixelsY);
    vec4 here = getColor(uv);
    vec4 left = getColor(uv - vec2(pixel.x, 0.0));
    vec4 right = getColor(uv + vec2(pixel.x, 0.0));
    vec4 down = getColor(uv - vec2(0.0, pixel.y));
    vec4 up = getColor(uv + vec2(0.0, pixel.y));
    if (length(left - right) < 0.02 && length(here - left) >= 0.02) {
        return left;
    }
    if (length(down - up) < 0.02 && length(here - down) >= 0.02) {
        return down;
    }
    return here;
}
