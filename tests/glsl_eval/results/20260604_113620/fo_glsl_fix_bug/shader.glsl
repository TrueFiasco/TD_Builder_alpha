out vec4 fragColor;
void main() {
    vec3 a = vec3(0.5, 0.4, 0.3);
    vec2 b = a;  // cannot convert vec3 -> vec2
    fragColor = TDOutputSwizzle(vec4(b, 0.0, 1.0));
}
