uniform vec3 uColor;
out vec4 fragColor;
uniform vec3 uColor;   // duplicate -- redefinition error
void main() {
    fragColor = TDOutputSwizzle(vec4(uColor, 1.0));
}
