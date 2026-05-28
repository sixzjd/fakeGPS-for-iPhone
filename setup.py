from setuptools import setup, find_packages

setup(
    name="fakegps",
    version="6.0.0",
    description="FakeGPS - iPhone virtual GPS location tool (cross-platform)",
    author="sixzjd",
    license="MIT",
    packages=find_packages(),
    package_data={"fakegps": ["map.html"]},
    entry_points={
        "console_scripts": [
            "fakegps=fakegps.cli:main",
        ],
    },
    install_requires=[
        "pymobiledevice3>=7.0",
    ],
    extras_require={
        "gui": ["PyQt6>=6.5", "PyQt6-WebEngine>=6.5"],
    },
    python_requires=">=3.9",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
    ],
)
