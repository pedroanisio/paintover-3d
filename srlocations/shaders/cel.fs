// A lit pass reduced to two tones, to multiply over flat colour: white in the light, a tint in the shade.
uniform float cut; // = 0.5
uniform float shadeR; // = 0.6
uniform float shadeG; // = 0.6
uniform float shadeB; // = 0.7

vec4 effect(vec2 uv) {
    vec4 lit = getColor(uv);
    float tone = dot(lit.rgb, vec3(0.3, 0.59, 0.11));
    return vec4(tone < cut ? vec3(shadeR, shadeG, shadeB) : vec3(1.0), lit.a);
}
