"""Setup script for TouchDesigner Unified Builder/Validator System."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="touchdesigner-unified-system",
    version="2.0.0",
    description="Unified builder/validator system for TouchDesigner networks",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="TD Builder Team",
    python_requires=">=3.8",
    packages=find_packages(exclude=["tests", "tests.*", "examples", "examples.*"]),
    install_requires=[
        "jsonschema>=4.0.0",  # JSON schema validation
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "td-validate=cli.td_validate:main",
            "td-convert=cli.td_convert:main",
            "td-build=cli.td_build:main",
        ]
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
