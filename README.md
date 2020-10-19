# PySegmentKit

> A python-port of [julius-speech/segmentation-kit](https://github.com/julius-speech/segmentation-kit)

- No more Perl
- No more edit original script to set options

## Usage

```python
from PySegmentKit import PySegmentKit, PSKError

    sk = PySegmentationKit(args.data_dir,
        disable_silence_at_ends=args.disable_silence_at_ends,
        leave_dict=args.leave_dict,
        debug=args.debug,
        triphone=args.triphone,
        input_mfcc=args.input_mfcc)

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

- PyPI (future work)

```shell
$ pip install PySegmentKit
```

## Use as a CLI

- Copy

```shell
$ git clone https://github.com/urushiyama/PySegmentKit.git
$ python PySegmentKit/__init__.py
```
