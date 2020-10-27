#!/usr/bin/env python
""" Python-ported version of julius segmentation-kit

This module is a python port of segmentation-kit perl script.

Example call:
    from PySegmentKit import PySegmentKit, PSKError

    sk = PySegmentKit(args.data_dir,
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

If you run main.py itself, it works as Command Line Interface (CLI).
CLI usage:
    python main.py [data_dir] [--disable-silence-at-ends] [--leave-dict] [--debug] [--triphone] [--input-mfcc]

    Segment files under data_dir.

    positional arguments:
     data_dir    a directory in which target files exists

    optional arguments:
     -h, --help                 show this help message and exit
     --disable-silence-at-ends  disable inserting silence at begin/end of sentence (default: keep inserting)
     --leave-dict               keep generated dfa and dict file (default: delete those files after processing)
     --debug                    output detailed julius debug message in log (default: do not output message)
     --triphone                 use triphone model (default: use monophone model)
     --input-mfcc               use MFCC file for input (default: use raw speech file)

Ported by urushiyama <aswif10flis1ntkb@gmail.com>
Original source: https://github.com/julius-speech/segmentation-kit
"""
#
# forced alignment using Julius
#
# usage: segment_julius.py dir
#
#   "dir" is a directory that contains waveform files and transcription files:
#
#     *.wav     Speech file (.wav, 16bit, 16kHz, PCM, no compression)
#     *.txt     Hiragana transcription of the speech file
#
#   All the *.wav data will be processed, and each result will be output
#   in these files:
#
#     *.lab     alignment result in Wavesurfer format
#
#   The following files are also output for debug:
#
#     *.log     julius log for debug
#     *.dfa     grammar file used by Julius
#     *.dict    dictionary file used by Julius
#
#   To see the results, open .wav file by wavesurfer and create
#   "Transciption" pane to see it.

import os
import sys
from pathlib import Path
import argparse
import platform
import subprocess
import re

package_directory = os.path.dirname(os.path.abspath(__file__))

class PSKError(Exception):
    """ Base class for exceptions for this module."""
    pass

class EnvironmentError(PSKError):
    """ Raised when the system is not supported.

    Attributes:
        detected_platform -- expression of the detected platform
        message -- explanation of the error
    """

    def __init__(self, detected_platform: str, message: str):
        self.detected_platform = detected_platform
        self.message = message

class NoDataDirError(PSKError, FileNotFoundError):
    """ Raised when data-dir does not exist.
    """
    pass

class DataDirIsNotADirectoryError(PSKError, NotADirectoryError):
    """ Raised when data-dir is not a directory.
    """
    pass

class IntermediateFileError(PSKError, RuntimeError):
    """ Raised when intermediate file could not be created.
    """
    pass

class UnsupportedTranscriptError(PSKError, ValueError):
    """ Raised when transcript file contains unsupported token.
    """
    pass

class PySegmentKit:
    """ Object for phoneme segmentation.

    Attributes:
        data_dir -- a directory in which target files exists
        disable_silence_at_ends -- disable inserting silence at begin/end of sentence (default: keep inserting)
        leave-dict -- keep generated dfa and dict file (default: delete those files after processing)
        debug -- output detailed julius debug message in log (default: do not output message)
        triphone -- use triphone model (default: use monophone model)
        input-mfcc -- use MFCC file for input (default: use raw speech file)
    """

    # julius executable
    @property
    def julius_path(self):
        """ Returns Path object indicating the julius executable for each running environment.
        """
        pf = platform.system()
        if pf == 'Windows':
            return Path(package_directory).joinpath('./bin/windows/julius.exe')
        elif pf == 'Darwin':
            return Path(package_directory).joinpath('./bin/macos/julius')
        elif pf == 'Linux':
            return Path(package_directory).joinpath('./bin/linux/julius')
        else:
            raise EnvironmentError(pf, 'Detected platform is not supported by module \'{}\''.format(__name__))

    @property
    def offset_align(self):
        """ Returns calculated offset_align.
        """
        return self.offset / 2 / 10**3

    def __init__(self, data_dir: str, disable_silence_at_ends=False, leave_dict=False, debug=False, triphone=False, input_mfcc=False):
        self.data_dir=Path(data_dir)

        self.disable_silence_at_ends=disable_silence_at_ends
        self.leave_dict=leave_dict
        self.debug=debug

        self.triphone=triphone
        if triphone:
            # triphone model
            self.hmmdefs = Path(package_directory).joinpath('./models/hmmdefs_ptm_gid.binhmm') # triphone model
            self.hlist = Path(package_directory).joinpath('./models/logicalTri')
        else:
            self.hmmdefs = Path(package_directory).joinpath('./models/hmmdefs_monof_mix16_gid.binhmm') # monophone model
            self.hlist = None

        self.input_mfcc=input_mfcc
        if input_mfcc:
            self.optargs=['-input', 'htkparam']
        else:
            self.optargs=['-input', 'file']

        self.offset=25 # ms

    def segment(self):
        """ execute phoneme segmentation.
        """
        if not self.data_dir.exists():
            raise NoDataDirError('No such data directory: \'{}\''.format(str(self.data_dir)))
        if not self.data_dir.is_dir():
            raise DataDirIsNotADirectoryError('\'{}\' is not a directory'.format(str(self.data_dir)))

        files = []
        for item in self.data_dir.iterdir():
            if not item.is_file():
                continue
            if item.suffix != '.wav' and item.suffix != '.WAV':
                continue
            basename = "{}/{}".format(str(self.data_dir), item.stem)
            files.append(basename)
            if item.suffix == '.WAV':
                item.rename("{}.wav".format(basename))

        segmented = {}
        for basename in files:
            print("{}.wav".format(basename))

            # read transcription and convert to phoneme sequence
            words = []
            if not self.disable_silence_at_ends:
                words.append('silB')

            transcript = Path('{}.txt'.format(basename))
            with transcript.open(encoding='utf-8') as f:
                for line in f:
                    line = line.rstrip()
                    if re.fullmatch(r'^[ \t\n]*$', line):
                        continue
                    words.append(PySegmentKit.yomi2voca(line))

            if not self.disable_silence_at_ends:
                words.append('silE')

            # generate dfa and dict for Julius
            dfafile = Path('{}.dfa'.format(basename))
            dictfile = Path('{}.dict'.format(basename))
            if dfafile.exists() and dfafile.is_file():
                dfafile.unlink()
            if dictfile.exists() and dictfile.is_file():
                dictfile.unlink()
            with dfafile.open(mode='w', encoding='utf-8') as f:
                for i in range(len(words)):
                    f.write("{} {} {} 0 {}\n".format(i, len(words) - i - 1, i + 1, '1' if i == 0 else '0'))
                f.write("{} -1 -1 1 0\n".format(len(words)))

            wlist = {}
            with dictfile.open(mode='w', encoding='utf-8') as f:
                for i in range(len(words)):
                    f.write("{0} [w_{0}] {1}\n".format(i, words[i]))
                    wlist["w_{}".format(i)] = words[i]
            if not (dfafile.exists() and dfafile.is_file()):
                raise IntermediateFileError('Failed to make {}'.format(str(dfafile)))
            if not (dictfile.exists() and dictfile.is_file()):
                raise IntermediateFileError('Failed to make {}'.format(str(dictfile)))

            # execute Julius and store the output to log
            logfile = Path('{}.log'.format(basename))
            wavfile = Path('{}.wav'.format(basename))

            # ensure julius is executable
            os.chmod(str(self.julius_path), 0o755)

            command = [str(self.julius_path), '-h', str(self.hmmdefs), '-dfa', str(dfafile), '-v', str(dictfile)]
            command.append('-palign')
            if self.triphone:
                command += ['-hlist', str(self.hlist)]
            command += self.optargs
            if self.debug:
                command.append('-debug')
            with logfile.open(mode='w') as log:
                if hasattr(subprocess, 'STARTUPINFO'):
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    env = os.environ
                else:
                    si = None
                    env = None
                subprocess.run(command, input="{}\n".format(str(wavfile)), encoding='utf-8', stdout=log, stderr=subprocess.DEVNULL, startupinfo=si, env=env)

            if not self.leave_dict and dfafile.exists():
                dfafile.unlink()
            if not self.leave_dict and dictfile.exists():
                dictfile.unlink()

            # parse log and output result
            results = []
            resultfile = Path("{}.lab".format(basename))
            with resultfile.open(mode='w', encoding='utf-8') as result:
                with logfile.open(encoding='utf-8') as log:
                    reading_alignment = False
                    for line in log:
                        line = line.rstrip()
                        if re.search(r'begin forced alignment', line):
                            reading_alignment = True
                        if reading_alignment and re.match(r'\[', line):
                            if len(words) > 1:
                                matched = re.search(r'\[(w_\d+)\]', line)
                                if matched:
                                    line = re.sub(matched.groups()[0], wlist[matched.groups()[0]], line)
                            matched = re.search(r'\[ *(\d+) *(\d+)\] *[0-9\.-]+ *(.*)$', line)
                            beginframe, endframe, unit = matched.groups()
                            beginframe = int(beginframe)
                            endframe = int(endframe)
                            begintime = beginframe * 0.01
                            if beginframe != 0:
                                begintime += self.offset_align
                            endtime = (endframe + 1) * 0.01 + self.offset_align
                            result.write("{:.7f} {:.7f} {}\n".format(begintime, endtime, unit))
                            results.append((begintime, endtime, unit))
                        if re.search(r'end forced alignment', line):
                            reading_alignment = False

            print("Result saved in \"{}\".\n".format(str(resultfile)))
            segmented[basename] = results
        return segmented


    @classmethod
    def yomi2voca(cls, yomi: str):
        """ Convert yomi (hiragana) strings into vocal alphabets.
        """
        voca = (
            yomi.rstrip()
                .replace('う゛ぁ', ' b a')
                .replace('う゛ぃ', ' b i')
                .replace('う゛ぇ', ' b e')
                .replace('う゛ぉ', ' b o')
                .replace('う゛ゅ', ' by u')

                # 2文字からなる変換規則
                .replace('ぅ゛', ' b u')

                .replace('あぁ', ' a a')
                .replace('いぃ', ' i i')
                .replace('いぇ', ' i e')
                .replace('いゃ', ' y a')
                .replace('うぅ', ' u:')
                .replace('えぇ', ' e e')
                .replace('おぉ', ' o:')
                .replace('かぁ', ' k a:')
                .replace('きぃ', ' k i:')
                .replace('くぅ', ' k u:')
                .replace('くゃ', ' ky a')
                .replace('くゅ', ' ky u')
                .replace('くょ', ' ky o')
                .replace('けぇ', ' k e:')
                .replace('こぉ', ' k o:')
                .replace('がぁ', ' g a:')
                .replace('ぎぃ', ' g i:')
                .replace('ぐぅ', ' g u:')
                .replace('ぐゃ', ' gy a')
                .replace('ぐゅ', ' gy u')
                .replace('ぐょ', ' gy o')
                .replace('げぇ', ' g e:')
                .replace('ごぉ', ' g o:')
                .replace('さぁ', ' s a:')
                .replace('しぃ', ' sh i:')
                .replace('すぅ', ' s u:')
                .replace('すゃ', ' sh a')
                .replace('すゅ', ' sh u')
                .replace('すょ', ' sh o')
                .replace('せぇ', ' s e:')
                .replace('そぉ', ' s o:')
                .replace('ざぁ', ' z a:')
                .replace('じぃ', ' j i:')
                .replace('ずぅ', ' z u:')
                .replace('ずゃ', ' zy a')
                .replace('ずゅ', ' zy u')
                .replace('ずょ', ' zy o')
                .replace('ぜぇ', ' z e:')
                .replace('ぞぉ', ' z o:')
                .replace('たぁ', ' t a:')
                .replace('ちぃ', ' ch i:')
                .replace('つぁ', ' ts a')
                .replace('つぃ', ' ts i')
                .replace('つぅ', ' ts u:')
                .replace('つゃ', ' ch a')
                .replace('つゅ', ' ch u')
                .replace('つょ', ' ch o')
                .replace('つぇ', ' ts e')
                .replace('つぉ', ' ts o')
                .replace('てぇ', ' t e:')
                .replace('とぉ', ' t o:')
                .replace('だぁ', ' d a:')
                .replace('ぢぃ', ' j i:')
                .replace('づぅ', ' d u:')
                .replace('づゃ', ' zy a')
                .replace('づゅ', ' zy u')
                .replace('づょ', ' zy o')
                .replace('でぇ', ' d e:')
                .replace('どぉ', ' d o:')
                .replace('なぁ', ' n a:')
                .replace('にぃ', ' n i:')
                .replace('ぬぅ', ' n u:')
                .replace('ぬゃ', ' ny a')
                .replace('ぬゅ', ' ny u')
                .replace('ぬょ', ' ny o')
                .replace('ねぇ', ' n e:')
                .replace('のぉ', ' n o:')
                .replace('はぁ', ' h a:')
                .replace('ひぃ', ' h i:')
                .replace('ふぅ', ' f u:')
                .replace('ふゃ', ' hy a')
                .replace('ふゅ', ' hy u')
                .replace('ふょ', ' hy o')
                .replace('へぇ', ' h e:')
                .replace('ほぉ', ' h o:')
                .replace('ばぁ', ' b a:')
                .replace('びぃ', ' b i:')
                .replace('ぶぅ', ' b u:')
                .replace('ふゃ', ' hy a')
                .replace('ぶゅ', ' by u')
                .replace('ふょ', ' hy o')
                .replace('べぇ', ' b e:')
                .replace('ぼぉ', ' b o:')
                .replace('ぱぁ', ' p a:')
                .replace('ぴぃ', ' p i:')
                .replace('ぷぅ', ' p u:')
                .replace('ぷゃ', ' py a')
                .replace('ぷゅ', ' py u')
                .replace('ぷょ', ' py o')
                .replace('ぺぇ', ' p e:')
                .replace('ぽぉ', ' p o:')
                .replace('まぁ', ' m a:')
                .replace('みぃ', ' m i:')
                .replace('むぅ', ' m u:')
                .replace('むゃ', ' my a')
                .replace('むゅ', ' my u')
                .replace('むょ', ' my o')
                .replace('めぇ', ' m e:')
                .replace('もぉ', ' m o:')
                .replace('やぁ', ' y a:')
                .replace('ゆぅ', ' y u:')
                .replace('ゆゃ', ' y a:')
                .replace('ゆゅ', ' y u:')
                .replace('ゆょ', ' y o:')
                .replace('よぉ', ' y o:')
                .replace('らぁ', ' r a:')
                .replace('りぃ', ' r i:')
                .replace('るぅ', ' r u:')
                .replace('るゃ', ' ry a')
                .replace('るゅ', ' ry u')
                .replace('るょ', ' ry o')
                .replace('れぇ', ' r e:')
                .replace('ろぉ', ' r o:')
                .replace('わぁ', ' w a:')
                .replace('をぉ', ' o:')

                .replace('う゛', ' b u')
                .replace('でぃ', ' d i')
                .replace('でぇ', ' d e:')
                .replace('でゃ', ' dy a')
                .replace('でゅ', ' dy u')
                .replace('でょ', ' dy o')
                .replace('てぃ', ' t i')
                .replace('てぇ', ' t e:')
                .replace('てゃ', ' ty a')
                .replace('てゅ', ' ty u')
                .replace('てょ', ' ty o')
                .replace('すぃ', ' s i')
                .replace('ずぁ', ' z u a')
                .replace('ずぃ', ' z i')
                .replace('ずぅ', ' z u')
                .replace('ずゃ', ' zy a')
                .replace('ずゅ', ' zy u')
                .replace('ずょ', ' zy o')
                .replace('ずぇ', ' z e')
                .replace('ずぉ', ' z o')
                .replace('きゃ', ' ky a')
                .replace('きゅ', ' ky u')
                .replace('きょ', ' ky o')
                .replace('しゃ', ' sh a')
                .replace('しゅ', ' sh u')
                .replace('しぇ', ' sh e')
                .replace('しょ', ' sh o')
                .replace('ちゃ', ' ch a')
                .replace('ちゅ', ' ch u')
                .replace('ちぇ', ' ch e')
                .replace('ちょ', ' ch o')
                .replace('とぅ', ' t u')
                .replace('とゃ', ' ty a')
                .replace('とゅ', ' ty u')
                .replace('とょ', ' ty o')
                .replace('どぁ', ' d o a')
                .replace('どぅ', ' d u')
                .replace('どゃ', ' dy a')
                .replace('どゅ', ' dy u')
                .replace('どょ', ' dy o')
                .replace('どぉ', ' d o:')
                .replace('にゃ', ' ny a')
                .replace('にゅ', ' ny u')
                .replace('にょ', ' ny o')
                .replace('ひゃ', ' hy a')
                .replace('ひゅ', ' hy u')
                .replace('ひょ', ' hy o')
                .replace('みゃ', ' my a')
                .replace('みゅ', ' my u')
                .replace('みょ', ' my o')
                .replace('りゃ', ' ry a')
                .replace('りゅ', ' ry u')
                .replace('りょ', ' ry o')
                .replace('ぎゃ', ' gy a')
                .replace('ぎゅ', ' gy u')
                .replace('ぎょ', ' gy o')
                .replace('ぢぇ', ' j e')
                .replace('ぢゃ', ' j a')
                .replace('ぢゅ', ' j u')
                .replace('ぢょ', ' j o')
                .replace('じぇ', ' j e')
                .replace('じゃ', ' j a')
                .replace('じゅ', ' j u')
                .replace('じょ', ' j o')
                .replace('びゃ', ' by a')
                .replace('びゅ', ' by u')
                .replace('びょ', ' by o')
                .replace('ぴゃ', ' py a')
                .replace('ぴゅ', ' py u')
                .replace('ぴょ', ' py o')
                .replace('うぁ', ' u a')
                .replace('うぃ', ' w i')
                .replace('うぇ', ' w e')
                .replace('うぉ', ' w o')
                .replace('ふぁ', ' f a')
                .replace('ふぃ', ' f i')
                .replace('ふぅ', ' f u')
                .replace('ふゃ', ' hy a')
                .replace('ふゅ', ' hy u')
                .replace('ふょ', ' hy o')
                .replace('ふぇ', ' f e')
                .replace('ふぉ', ' f o')

                # 1音からなる変換規則
                .replace('あ', ' a')
                .replace('い', ' i')
                .replace('う', ' u')
                .replace('え', ' e')
                .replace('お', ' o')
                .replace('か', ' k a')
                .replace('き', ' k i')
                .replace('く', ' k u')
                .replace('け', ' k e')
                .replace('こ', ' k o')
                .replace('さ', ' s a')
                .replace('し', ' sh i')
                .replace('す', ' s u')
                .replace('せ', ' s e')
                .replace('そ', ' s o')
                .replace('た', ' t a')
                .replace('ち', ' ch i')
                .replace('つ', ' ts u')
                .replace('て', ' t e')
                .replace('と', ' t o')
                .replace('な', ' n a')
                .replace('に', ' n i')
                .replace('ぬ', ' n u')
                .replace('ね', ' n e')
                .replace('の', ' n o')
                .replace('は', ' h a')
                .replace('ひ', ' h i')
                .replace('ふ', ' f u')
                .replace('へ', ' h e')
                .replace('ほ', ' h o')
                .replace('ま', ' m a')
                .replace('み', ' m i')
                .replace('む', ' m u')
                .replace('め', ' m e')
                .replace('も', ' m o')
                .replace('ら', ' r a')
                .replace('り', ' r i')
                .replace('る', ' r u')
                .replace('れ', ' r e')
                .replace('ろ', ' r o')
                .replace('が', ' g a')
                .replace('ぎ', ' g i')
                .replace('ぐ', ' g u')
                .replace('げ', ' g e')
                .replace('ご', ' g o')
                .replace('ざ', ' z a')
                .replace('じ', ' j i')
                .replace('ず', ' z u')
                .replace('ぜ', ' z e')
                .replace('ぞ', ' z o')
                .replace('だ', ' d a')
                .replace('ぢ', ' j i')
                .replace('づ', ' z u')
                .replace('で', ' d e')
                .replace('ど', ' d o')
                .replace('ば', ' b a')
                .replace('び', ' b i')
                .replace('ぶ', ' b u')
                .replace('べ', ' b e')
                .replace('ぼ', ' b o')
                .replace('ぱ', ' p a')
                .replace('ぴ', ' p i')
                .replace('ぷ', ' p u')
                .replace('ぺ', ' p e')
                .replace('ぽ', ' p o')
                .replace('や', ' y a')
                .replace('ゆ', ' y u')
                .replace('よ', ' y o')
                .replace('わ', ' w a')
                .replace('ゐ', ' i')
                .replace('ゑ', ' e')
                .replace('ん',' N')
                .replace('っ', ' q')
                .replace('ー', ':')

                # ここまでに処理されてない ぁぃぅぇぉ はそのまま大文字扱い
                .replace('ぁ', ' a')
                .replace('ぃ', ' i')
                .replace('ぅ', ' u')
                .replace('ぇ', ' e')
                .replace('ぉ', ' o')
                .replace('ゎ', ' w a')
                .replace('ぉ', ' o')

                #その他特別なルール
                .replace('を', ' o')
        )

        voca = re.sub(r'^ ([a-z]+)', r'\1', voca).replace(':+', ':')

        unsupported = re.search(r'[^ a-zA-Z:]+', voca)
        if unsupported:
            raise UnsupportedTranscriptError('Unsupported character(s) is in the transcript: {}'.format(unsupported.group()))

        return voca


if __name__ == '__main__':
    # works as command line tool
    parser = argparse.ArgumentParser(description='Segment files under data_dir.')
    parser.add_argument('data_dir', metavar='data-var', nargs='?', default='./wav', help='directory that contains waveform files and transcription files (default: \'./wav\'')
    # original flags also can be set by args
    parser.add_argument('--disable-silence-at-ends', action='store_true', help='disable inserting silence at begin/end of sentence (default: keep inserting)')
    parser.add_argument('--leave-dict', action='store_true', help='keep generated dfa and dict file (default: delete those files after processing)')
    parser.add_argument('--debug', action='store_true', help='output detailed julius debug message in log (default: do not output message)')
    # original comment-outs also can be set by args
    parser.add_argument('--triphone', action='store_true', help='use triphone model (default: use monophone model)')
    parser.add_argument('--input-mfcc', action='store_true', help='use MFCC file for input (default: use raw speech file)')

    args = parser.parse_args()

    sk = PySegmentKit(args.data_dir,
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
