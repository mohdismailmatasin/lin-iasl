#!/usr/bin/env python3
"""Setup configuration for Lin-IASL package."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="lin-iasl",
    version="1.0.0",
    author="Lin-IASL Contributors",
    description="ACPI Table Editor for Linux - Compile, decompile, and edit ACPI tables",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/lin-iasl",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "PyGObject>=3.40",
    ],
    extras_require={
        "linux": [
            "gir1.2-gtksource-3.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "lin-iasl=lin_iasl.main:main",
        ],
    },
)