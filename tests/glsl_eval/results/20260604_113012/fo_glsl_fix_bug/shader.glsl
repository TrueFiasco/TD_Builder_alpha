out vec4 fragColor;
void main() {
    float active = 0.5;     // 'active' is reserved in some profiles
    fragColor = TDOutputSwizzle(vec4(active, active, active, 1.0));
}
