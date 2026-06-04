#!/usr/bin/env python3
"""
Teardrop TOE Builder

Creates a working TouchDesigner project for the Teardrop visual system:
- Embeds audioAnalysis palette component
- Creates audio-reactive visual chain
- Proper feedback loop with noise displacement
- Bloom post-processing
- Render output
"""

import shutil
import struct
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

# Paths
TOECOLLAPSE = r"C:\Program Files\Derivative\TouchDesigner\bin\toecollapse.exe"
PALETTE_DIR = Path(r"C:\TD_Projects\Learn\Palette\Tools")
OUTPUT_DIR = Path(__file__).parent / "test_output" / "teardrop_v2_subagent"


class TeardropBuilder:
    """Builds a complete Teardrop TOE project."""

    def __init__(self, output_dir: Path = OUTPUT_DIR, verbose: bool = True):
        self.output_dir = Path(output_dir)
        self.verbose = verbose
        self.toc_entries = []

    def log(self, msg: str):
        if self.verbose:
            print(msg)

    def build(self) -> Optional[Path]:
        """Build the complete Teardrop TOE."""
        self.log("\n" + "=" * 60)
        self.log("Building Teardrop TOE")
        self.log("=" * 60)

        # Setup directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        project_dir = self.output_dir / "teardrop_full.toe.dir"
        if project_dir.exists():
            shutil.rmtree(project_dir)
        project_dir.mkdir(parents=True)

        self.project_dir = project_dir
        self.toc_entries = []

        # 1. Create system files
        self._write_system_files()

        # 2. Create main project container
        self._write_project_container()

        # 3. Embed audioAnalysis palette component
        self._embed_audio_analysis()

        # 4. Create visual chain
        self._create_visual_chain()

        # 5. Create render output
        self._create_render_output()

        # 6. Write TOC
        toc_path = self._write_toc()

        # 7. Collapse to TOE
        toe_path = self._collapse(toc_path)

        if toe_path:
            self.log("\n" + "=" * 60)
            self.log(f"[SUCCESS] Created: {toe_path}")
            self.log(f"         Size: {toe_path.stat().st_size} bytes")
            self.log("=" * 60)

        return toe_path

    def _write_system_files(self):
        """Write root-level system files for TOE."""
        self.log("\n[1/6] Writing system files...")

        # .build
        self._write_file(".build", "version 099\nbuild 2023.11880\n")

        # .start (timing/playback)
        self._write_file(".start", """?
perform 0 on
realtime 0 on
cookrate 0 60
?
""")

        # .grps (groups)
        self._write_file(".grps", "-2\n0\n")

        # .root
        self._write_file(".root", "end\n")

        # .parm (root params)
        self._write_file(".parm", "?\n?\n")

        self.log("  Created 5 system files")

    def _write_project_container(self):
        """Create main project container."""
        self.log("\n[2/6] Creating project container...")

        # Main container .n file
        self._write_file("project1.n", """COMP:container
tile 0 0 500 400
flags =  parlanguage 0
end
""")

        # Main container .parm
        self._write_file("project1.parm", """?
w 0 1920
h 0 1080
?
""")

        # Main container .panel
        self._write_file("project1.panel", """?
screenw 0 1920
screenh 0 1080
?
""")

        # Create project1 directory
        (self.project_dir / "project1").mkdir(exist_ok=True)

        self.log("  Created project container")

    def _embed_audio_analysis(self):
        """Embed audioAnalysis palette component."""
        self.log("\n[3/6] Embedding audioAnalysis palette component...")

        source_dir = PALETTE_DIR / "audioAnalysis.tox.dir"
        if not source_dir.exists():
            self.log(f"  [WARNING] audioAnalysis not found at {source_dir}")
            self._create_simple_audio_chain()
            return

        # Navigate to inner component (skip 2 wrapper levels)
        inner_path = source_dir / "audioAnalysis" / "audioAnalysis"
        if not inner_path.exists():
            self.log(f"  [WARNING] Inner path not found: {inner_path}")
            self._create_simple_audio_chain()
            return

        # Copy root component files
        dst_dir = self.project_dir / "project1"
        for ext in ['.n', '.parm', '.cparm', '.panel', '.network']:
            src_file = inner_path.parent / f"audioAnalysis{ext}"
            if src_file.exists():
                dst_file = dst_dir / f"audio{ext}"
                shutil.copy2(src_file, dst_file)
                self.toc_entries.append(f"project1/audio{ext}")

        # Copy all child content
        if inner_path.is_dir():
            audio_dst = dst_dir / "audio"
            audio_dst.mkdir(exist_ok=True)
            self._copy_recursive(inner_path, audio_dst, "project1/audio")

        self.log(f"  Embedded audioAnalysis ({len([e for e in self.toc_entries if 'audio' in e])} files)")

    def _create_simple_audio_chain(self):
        """Fallback: create simple audio chain if palette not available."""
        self.log("  Creating simple audio chain fallback...")

        # audiodevicein
        self._write_file("project1/audiodevicein1.n", """CHOP:audioDeviceIn
tile 0 0 130 90
flags =  parlanguage 0
end
""")
        self._write_file("project1/audiodevicein1.parm", """?
active 0 on
?
""")

        # analyze
        self._write_file("project1/analyze1.n", """CHOP:analyze
tile 150 0 130 90
flags =  parlanguage 0
inputs
{
0	audiodevicein1
}
end
""")
        self._write_file("project1/analyze1.parm", """?
function 0 average
?
""")

        # null for audio output
        self._write_file("project1/null_audio.n", """CHOP:null
tile 300 0 130 90
flags =  parlanguage 0
inputs
{
0	analyze1
}
end
""")
        self._write_file("project1/null_audio.parm", "?\n?\n")

    def _create_visual_chain(self):
        """Create the visual processing chain."""
        self.log("\n[4/6] Creating visual chain...")

        dst_dir = self.project_dir / "project1"

        # Noise TOP (base texture)
        self._write_file("project1/noise1.n", """TOP:noise
tile 0 200 130 90
flags =  viewer 1 parlanguage 0
end
""")
        self._write_file("project1/noise1.parm", """?
resolutionw 0 1920
resolutionh 0 1080
type 0 perlin
period 17 10 op('audio/out1')['low'] * 20 + 5
amp 0 1
harmonics 0 4
?
""")

        # Ramp TOP (radial gradient for pulse)
        self._write_file("project1/ramp1.n", """TOP:ramp
tile 0 300 130 90
flags =  parlanguage 0
end
""")
        self._write_file("project1/ramp1.parm", """?
resolutionw 0 1920
resolutionh 0 1080
type 0 radial
phase 17 0 op('audio/out1')['low'] * 0.5
?
""")

        # Level (color the ramp - amber/gold)
        self._write_file("project1/level1.n", """TOP:level
tile 150 300 130 90
flags =  parlanguage 0
inputs
{
0	ramp1
}
end
""")
        self._write_file("project1/level1.parm", """?
opacity 17 1 0.5 + op('audio/out1')['low'] * 0.5
blacklevel 0 0
brightness 0 1.2
gamma 0 0.9
?
""")

        # Composite (combine noise and ramp)
        self._write_file("project1/comp1.n", """TOP:composite
tile 300 250 130 90
flags =  parlanguage 0
inputs
{
0	noise1
1	level1
}
end
""")
        self._write_file("project1/comp1.parm", """?
operand 0 add
?
""")

        # Feedback TOP
        self._write_file("project1/feedback1.n", """TOP:feedback
tile 450 250 130 90
flags =  parlanguage 0
inputs
{
0	blur1
}
end
""")
        self._write_file("project1/feedback1.parm", """?
top 0 blur1
?
""")

        # Composite with feedback
        self._write_file("project1/comp2.n", """TOP:composite
tile 450 350 130 90
flags =  parlanguage 0
inputs
{
0	comp1
1	feedback1
}
end
""")
        self._write_file("project1/comp2.parm", """?
operand 0 over
opacity 0 0.92
?
""")

        # Blur for feedback smoothing
        self._write_file("project1/blur1.n", """TOP:blur
tile 600 350 130 90
flags =  parlanguage 0
inputs
{
0	comp2
}
end
""")
        self._write_file("project1/blur1.parm", """?
filtertype 0 gaussian
filterwidth 17 3 2 + op('audio/out1')['mid'] * 5
?
""")

        # HSV adjust for color (amber/gold tint)
        self._write_file("project1/hsvadjust1.n", """TOP:hsvAdjust
tile 750 350 130 90
flags =  parlanguage 0
inputs
{
0	blur1
}
end
""")
        self._write_file("project1/hsvadjust1.parm", """?
hueoffset 0 0.08
saturationmult 0 0.7
valuemult 0 1.1
?
""")

        # Bloom (final glow)
        self._write_file("project1/bloom1.n", """TOP:bloom
tile 900 350 130 90
flags =  viewer 1 parlanguage 0
inputs
{
0	hsvadjust1
}
end
""")
        self._write_file("project1/bloom1.parm", """?
size 17 20 10 + op('audio/out1')['low'] * 40
threshold 0 0.5
strength 17 0.6 0.4 + op('audio/out1')['low'] * 0.4
?
""")

        self.log("  Created 10 visual operators")

    def _create_render_output(self):
        """Create render output."""
        self.log("\n[5/6] Creating render output...")

        # Out TOP (final output)
        self._write_file("project1/out1.n", """TOP:out
tile 1050 350 130 90
flags =  viewer 1 render on parlanguage 0
inputs
{
0	bloom1
}
end
""")
        self._write_file("project1/out1.parm", "?\n?\n")

        # Null for monitoring
        self._write_file("project1/null1.n", """TOP:null
tile 1050 450 130 90
flags =  viewer 1 parlanguage 0
inputs
{
0	bloom1
}
end
""")
        self._write_file("project1/null1.parm", "?\n?\n")

        self.log("  Created output operators")

    def _write_file(self, rel_path: str, content: str):
        """Write a file and add to TOC."""
        file_path = self.project_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8', newline='\n')
        self.toc_entries.append(rel_path)

    def _copy_recursive(self, src_dir: Path, dst_dir: Path, toc_prefix: str):
        """Recursively copy directory contents."""
        dst_dir.mkdir(parents=True, exist_ok=True)

        for item in src_dir.iterdir():
            if item.is_file():
                dst_file = dst_dir / item.name
                shutil.copy2(item, dst_file)
                # Handle versioned files (name.ext.N -> name.ext N in TOC)
                toc_name = self._file_to_toc_entry(item.name)
                self.toc_entries.append(f"{toc_prefix}/{toc_name}")
            elif item.is_dir():
                self._copy_recursive(
                    item,
                    dst_dir / item.name,
                    f"{toc_prefix}/{item.name}"
                )

    def _file_to_toc_entry(self, filename: str) -> str:
        """Convert versioned filename to TOC entry format."""
        import re
        match = re.match(r'^(.+\.[a-z]+)\.(\d+)$', filename)
        if match:
            return f"{match.group(1)} {match.group(2)}"
        return filename

    def _write_toc(self) -> Path:
        """Write TOC file with correct ordering."""
        self.log("\n[6/6] Writing TOC...")

        def toc_sort_key(filepath):
            ext_priority = {'.n': 0, '.cparm': 1, '.parm': 2, '.panel': 3, '.network': 4}
            parts = filepath.rsplit('.', 1)
            if len(parts) == 2:
                ext = '.' + parts[1]
                base = parts[0]
            else:
                ext = ''
                base = filepath
            priority = ext_priority.get(ext, 5)
            depth = filepath.count('/') + filepath.count('\\')
            return (depth, base, priority, filepath)

        sorted_entries = sorted(self.toc_entries, key=toc_sort_key)
        toc_content = '\n'.join(sorted_entries) + '\n'

        toc_path = self.output_dir / "teardrop_full.toe.toc"
        toc_path.write_text(toc_content, encoding='utf-8', newline='\n')

        self.log(f"  Created TOC with {len(sorted_entries)} entries")
        return toc_path

    def _collapse(self, toc_path: Path) -> Optional[Path]:
        """Collapse to TOE file."""
        toe_path = self.output_dir / "teardrop_full.toe"
        if toe_path.exists():
            toe_path.unlink()

        result = subprocess.run(
            [TOECOLLAPSE, str(self.project_dir)],
            capture_output=True,
            text=True
        )

        if toe_path.exists() and toe_path.stat().st_size > 100:
            return toe_path
        else:
            self.log(f"[ERROR] Collapse failed: {result.stderr}")
            return None


def main():
    builder = TeardropBuilder()
    result = builder.build()

    if result:
        print(f"\nOpen in TouchDesigner: {result}")
    else:
        print("\nBuild failed!")


if __name__ == '__main__':
    main()
