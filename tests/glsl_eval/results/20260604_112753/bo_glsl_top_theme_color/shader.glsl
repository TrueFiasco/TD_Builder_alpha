uniform float uTime;
out vec4 fragColor;
void main() {
    vec2 uv = vUV.st;
    float t = uTime;
    vec3 c = vec3(0.05 + 0.5 * uv.x, 0.1 + 0.4 * uv.y,
                  0.6 + 0.4 * sin(t + uv.x * 6.2831));
    fragColor = TDOutputSwizzle(vec4(c, 1.0));
}
