in vec2 vUV;   // TD already declares vUV -- triggers redefinition
out vec4 fragColor;
void main() {
    fragColor = TDOutputSwizzle(vec4(vUV, 0.0, 1.0));
}
