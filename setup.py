import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="PySegmentKit",
    version="0.2.1",
    author="Yuta Urushiyama",
    author_email="aswif10flis1ntkb@gmail.com",
    description="A python-port of julius-speech/segmentation-kit",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/urushiyama/PySegmentKit",
    packages=setuptools.find_packages(),
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    include_package_data=True,
)
