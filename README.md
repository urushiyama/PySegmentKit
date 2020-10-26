# PySegmentKit

> A python-port of [julius-speech/segmentation-kit](https://github.com/julius-speech/segmentation-kit)

- No more Perl
- No more edit original script to set options

## Usage

```python
from PySegmentKit import PySegmentKit, PSKError

sk = PySegmentKit(input(),
    disable_silence_at_ends=False,
    leave_dict=False,
    debug=False,
    triphone=False,
    input_mfcc=False)

try:
    segmented = sk.segment()
    for result in segmented.keys():
        print("=====Segmentation result of {}.wav=====".format(result))
        for begintime, endtime, unit in segmented[result]:
            print("{:.7f} {:.7f} {}".format(begintime, endtime, unit))
except PSKError as e:
    print(e)
```

## Install as a third-party library

- PyPI

```shell
$ pip install PySegmentKit
```

## Use as a CLI

- Copy

```shell
$ git clone https://github.com/urushiyama/PySegmentKit.git
$ python PySegmentKit/main.py -h # show detailed usage
```

## License

This library is released under MIT License.

The original perl script, [julius-speech/segmentation-kit](https://github.com/julius-speech/segmentation-kit), is released under MIT License. 

This library bundles some binaries of [Julius](https://github.com/julius-speech/julius), which is released under BSD 3-Clause "New" or "Revised" License.

Please refer to [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md) for detail.
