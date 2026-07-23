from setuptools import setup, find_packages

setup(
    name="fakegps",
    version="6.2.2",
    description="FakeGPS - iPhone virtual GPS location tool (cross-platform)",
    author="sixzjd",
    license="MIT",
    packages=find_packages(),
    package_data={"fakegps": ["ui.html"]},
    entry_points={
        "console_scripts": [
            "fakegps=fakegps.cli:main",
        ],
    },
    install_requires=[
        "pymobiledevice3>=7.0",
    ],
    extras_require={
        "gui": ["pywebview==5.4", "pythonnet==3.0.5", "clr-loader==0.2.7.post0"],
    },
    python_requires=">=3.9",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
    ],
)
