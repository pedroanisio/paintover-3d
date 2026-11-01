// Lines from an ID pass: a pixel is inked where a neighbour holds a different colour. With `shadow` above 0 it also
// darkens what lies beside an edge, as a sheet of paper does to the sheet under it.
uniform float pixelsX; // = 1280
uniform float pixelsY; // = 720
uniform float radius; // = 1
uniform float vary; // = 0
uniform float wobble; // = 0
uniform float inkR; // = 0
uniform float inkG; // = 0
uniform float inkB; // = 0
uniform float shadow; // = 0
uniform float shadowX; // = 0
uniform float shadowY; // = 0

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float bottom = mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x);
    float top = mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x);
    return mix(bottom, top, u.y);
}

float differs(vec4 here, vec2 at) {
    return step(0.02, length(here - getColor(at)));
}

vec4 effect(vec2 uv) {
    vec2 pixel = 1.0 / vec2(pixelsX, pixelsY);
    vec2 p = uv * vec2(pixelsX, pixelsY);
    vec2 q = uv + wobble * pixel * vec2(noise(p / 45.0) - 0.5, noise(p / 45.0 + 17.0) - 0.5) * 2.0;
    vec2 r = pixel * radius * (1.0 + vary * (noise(p / 70.0 + 5.0) - 0.5) * 2.0);
    vec4 here = getColor(q);
    float line = differs(here, q + vec2(r.x, 0.0));
    line = max(line, differs(here, q - vec2(r.x, 0.0)));
    line = max(line, differs(here, q + vec2(0.0, r.y)));
    line = max(line, differs(here, q - vec2(0.0, r.y)));
    line = max(line, differs(here, q + r * 0.7));
    line = max(line, differs(here, q - r * 0.7));
    line = max(line, differs(here, q + vec2(r.x, -r.y) * 0.7));
    line = max(line, differs(here, q + vec2(-r.x, r.y) * 0.7));
    vec2 reach = vec2(shadowX, shadowY) * pixel;
    float cast = differs(here, q + reach * 0.33) + differs(here, q + reach * 0.66) + differs(here, q + reach);
    float alpha = max(line, step(0.001, shadow) * shadow * cast / 3.0);
    return vec4(vec3(inkR, inkG, inkB) * step(0.5, line), alpha);
}
