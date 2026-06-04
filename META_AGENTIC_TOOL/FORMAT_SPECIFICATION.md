# TouchDesigner .tox/.toe File Format Specification

Based on analysis of 640 expanded ground-truth .tox files with 18,084 parameters.

## Overview

TouchDesigner projects consist of:
- `.toe` files - complete projects
- `.tox` files - component exports (reusable modules)

Both can be expanded using `toeexpand` into a directory structure for editing, then collapsed back with `toecollapse`.

## Directory Structure

```
project.toe.dir/           # Expanded directory
├── .build                 # Build/version metadata
├── .start                 # Runtime settings (toe only)
├── .root                  # Root component path (toe only)
├── .grps                  # Groups file (toe only)
├── .parm                  # Root parameters (toe only)
├── .application           # UI layout (toe only)
├── project1.n             # Root component definition
├── project1.parm          # Root component parameters
├── project1/              # Children of project1
│   ├── noise1.n           # Operator definition
│   ├── noise1.parm        # Operator parameters
│   ├── text1.n
│   ├── text1.parm
│   └── text1.text         # Extra file (Text DAT content)
└── project1/base1/        # Nested COMP children
    └── ...

project.toe.toc            # Table of contents
```

## .toc File Format

The `.toc` file lists all files in the expanded directory in order.

```
# 4 0 0 0 1
.build
project1.n
project1.parm
project1/noise1.n
project1/noise1.parm
```

### Header Line
`# {format_version} {flag1} {flag2} {flag3} {flag4}`

- Format version: 4 (current)
- Flags: Meaning TBD (always "0 0 0 1" in observed samples)

### File Order
Files must be listed in dependency order:
1. `.build` (always first)
2. `.start`, `.root`, `.grps`, `.parm`, `.application` (toe only)
3. Operators in hierarchical order (parent before children)

---

## .build File Format

Contains build metadata.

```
version 099
build 2023.11880
time Sep 12 2023 - 19:44:17
osname Windows
osversion 10.0.19045
```

### Fields
| Field | Description |
|-------|-------------|
| version | TD version (099 = 2023) |
| build | Build number |
| time | Build timestamp |
| osname | Operating system |
| osversion | OS version |

---

## .start File Format (toe only)

Runtime settings.

```
cookrate 60
realtime on
clock 0 0 0
```

### Fields
| Field | Description |
|-------|-------------|
| cookrate | Frames per second |
| realtime | `on` or `off` |
| clock | Clock settings |

---

## .n File Format (Operator Definition)

Defines an operator's type, position, and connections.

```
CHOP:constant
v 0 0 1
tile 100 200 130 90
flags = display on render off current on parlanguage 0
inputs
{
0 	noise1
1 	lfo1
}
color 0.67 0.67 0.67
end
```

### Sections

#### Type Line (Required)
`{FAMILY}:{type}`

Examples:
- `CHOP:constant`
- `TOP:blur`
- `SOP:sphere`
- `COMP:base`

#### Viewport Position (Optional)
`v {x} {y} {z}`

3D position in network editor.

#### Tile Position (Optional)
`tile {x} {y} {width} {height}`

2D tile position and size.

#### Flags (Optional)
`flags = {key} {value} ...`

Common flags:
| Flag | Values | Description |
|------|--------|-------------|
| display | on/off | Blue flag (view output) |
| render | on/off | Purple flag (render) |
| current | on/off | Currently selected |
| bypass | on/off | Bypass cooking |
| lock | on/off | Lock parameters |
| viewer | on/off | Viewer active |
| parlanguage | 0/1 | 0=Python, 1=Tscript |

#### Inputs Block (Optional)
```
inputs
{
{input_index} 	{source_operator}
}
```

- Tab character between index and source
- Source can be relative name or absolute path
- Index is 0-based

#### Color (Optional)
`color {r} {g} {b}`

RGB values 0.0-1.0

#### End (Required)
`end`

---

## .parm File Format (Parameters)

Contains non-default parameter values.

```
?
const0name 0 my_channel
const0value 0 1.5
rate 16 60 me.time.rate
?
```

### Structure
```
?
{param_name} {mode} {value} [expression]
...
?
```

- Starts and ends with `?` sentinel
- Only non-default values are written
- Default values are NOT stored

### Mode Numbers

| Mode | Binary | Meaning |
|------|--------|---------|
| 0 | 0b0 | Constant value |
| 16 | 0b10000 | Expression (Python/Tscript) |
| 256 | 0b100000000 | Special (COMP shortcuts) |
| 1024 | 0b10000000000 | Password/masked |
| 524288 | 0b10000000000000000000 | POP param flag |
| 1048576 | 0b100000000000000000000 | POP param flag |

### Expression Format (Mode 16)
```
{param_name} 16 {constant_fallback} {expression}
```

Example:
```
rate 16 60.1234 me.time.rate
file 16 $TFS/audio.mp3 app.samplesFolder+'/audio.mp3'
```

### Value Types
| Type | Format | Example |
|------|--------|---------|
| Integer | Plain number | `5` |
| Float | Decimal | `1.5` |
| String | Unquoted | `my_file.txt` |
| Menu | Menu value name | `gaussian` |
| Toggle | `on` or `off` | `on` |

---

## Extra File Types

| Extension | Description | Operator Types |
|-----------|-------------|----------------|
| .text | Text content | Text DAT |
| .table | Table data | Table DAT |
| .panel | Panel config | All COMPs |
| .geo | Geometry data | File In SOP |
| .py | Python script | Script DAT |

---

## Parameter Discovery

**Critical**: TD only writes parameters that differ from defaults.

To discover all parameters for an operator:
1. Create operator in TD
2. Set ALL parameters to non-default values
3. Save as .tox
4. Expand with toeexpand
5. Parse .parm file

This project has captured 18,084 parameters across 630 operators using this method.

---

## Building New Files

### Minimal .tox Structure
```
# 4 0 0 0 1
.build
container.n
container.parm
container/my_op.n
container/my_op.parm
```

### Steps to Create
1. Create `.build` with version info
2. Create container `.n` file (COMP:base)
3. Create container `.parm` (can be `?\n?\n`)
4. Create child operator `.n` files
5. Create child operator `.parm` files (non-defaults only)
6. Write `.toc` with all files
7. Run `toecollapse {name}.tox.toc`

---

## Common Patterns

### Multi-Value Parameters
Some parameters have indexed components:

```
const0name 0 chan1
const0value 0 1.0
const1name 0 chan2
const1value 0 2.0
```

Pattern: `{base}{index}{suffix}`

Known patterns:
| Operator | Pattern | Range |
|----------|---------|-------|
| Constant CHOP | const{N}name, const{N}value | 0-39 |
| GLSL TOP | uniname{N}, value{N}x/y/z/w | 0-15 |
| Geometry COMP | instance{N}op/tx/ty/tz | 0-9 |

### Operator Families
| Family | Description |
|--------|-------------|
| CHOP | Channel Operators (signals) |
| TOP | Texture Operators (images) |
| SOP | Surface Operators (geometry) |
| DAT | Data Operators (tables, text) |
| MAT | Material Operators (shaders) |
| COMP | Component Operators (containers) |
| POP | Particle Operators |

---

## File Statistics (Ground Truth)

| Metric | Value |
|--------|-------|
| Operators analyzed | 630 |
| Parameters captured | 18,084 |
| Unique param names | 5,468 |
| Mode 0 (constant) | 17,757 |
| Mode 16 (expression) | 171 |
| Other modes | 156 |
