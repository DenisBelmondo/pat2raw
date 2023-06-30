import io
import struct
from dataclasses import dataclass, field
from enum import auto, IntEnum, IntFlag


class Error(IntEnum):
    OK = auto()
    BAD_HEADER = auto()
    TOO_MANY_INSTRUMENTS = auto()
    TOO_MANY_LAYERS = auto()


class Mode(IntFlag):
    SIXTEEN_BIT = 1
    UNSIGNED = 1 << 1
    LOOPING = 1 << 2
    PINGPONG = 1 << 3
    REVERSE = 1 << 4
    SUSTAIN = 1 << 5
    ENVELOPE = 1 << 6
    CLAMPED = 1 << 7


@dataclass(init=True, repr=True)
class Audio:
    pcm_data: bytearray = bytearray()
    sample_width_in_bytes: int = 1


@dataclass(init=True, repr=True)
class Result:
    error: Error = Error.OK
    error_msg: str = ''
    samples: list[Audio] = field(default_factory=list)


FRACTION_BITS = 12


def read(path) -> Result:
    result = Result()

    with io.open(path, 'rb') as f:
        id = f.read(11)
        if id != b'GF1PATCH110' and id != b'GF1PATCH100':
            result.error = Error.BAD_HEADER
            result.error_msg = 'Invalid Gravis patch file.'
            return result

        # timidity: instruments. To some patch makers, 0 means 1
        f.seek(82, io.SEEK_SET)
        num_instruments = int.from_bytes(f.read(1), 'little')
        num_instruments += num_instruments == 0
        if num_instruments <= 0:
            result.error = Error.TOO_MANY_INSTRUMENTS
            result.error_msg = f'Cannot handle patches with {num_instruments} instruments.'
            return result

        # timidity: layers. What's a layer?
        f.seek(151, io.SEEK_SET)
        num_layers = int.from_bytes(f.read(1), 'little')
        num_layers += num_layers == 0
        if num_layers <= 0:
            result.error = Error.TOO_MANY_LAYERS
            result.error_msg = f'Cannot handle patches with {num_layers} layers.'
            return result

        f.seek(198, io.SEEK_SET)
        num_samples = int.from_bytes(f.read(1), 'little')

        # skip reserved bytes
        f.seek(40, io.SEEK_CUR)

        for _ in range(num_samples):
            # timidity: skip the wave name
            f.seek(7, io.SEEK_CUR)

            # according to http://www33146ue.sakura.ne.jp/staff/iz/formats/guspat.html
            # bit 0..3: Loop offset start fractions [0/16 .. 15/16]
            # bit 4..7: Loop offset end fractions [0/16 .. 15/16]
            fractions = int.from_bytes(f.read(1), 'little')

            data_length = int.from_bytes(f.read(4), 'little')
            loop_start = int.from_bytes(f.read(4), 'little')
            loop_end = int.from_bytes(f.read(4), 'little')
            sample_rate = int.from_bytes(f.read(2), 'little')
            low_freq = int.from_bytes(f.read(4), 'little')
            high_freq = int.from_bytes(f.read(4), 'little')
            root_freq = int.from_bytes(f.read(4), 'little')
            # timidity: why have a "root frequency" and then "tuning"??
            f.seek(2, io.SEEK_CUR)
            stereo_balance = int.from_bytes(f.read(1), 'little')
            # timidity: envelope, tremolo, and vibrato
            f.seek(12, io.SEEK_CUR)
            tremolo_sweep = int.from_bytes(f.read(1), 'little')
            tremolo_rate = int.from_bytes(f.read(1), 'little')
            tremolo_depth = int.from_bytes(f.read(1), 'little')
            # if not tremolo_sweep or not tremolo_rate:
            #     print('no tremolo')
            vibrato_sweep = int.from_bytes(f.read(1), 'little')
            vibrato_rate = int.from_bytes(f.read(1), 'little')
            vibrato_depth = int.from_bytes(f.read(1), 'little')
            modes = Mode(int.from_bytes(f.read(1), 'little'))
            scale_freq = int.from_bytes(f.read(2), 'little')
            scale_factor = int.from_bytes(f.read(2), 'little')

            # timidity: skip reserved space
            f.seek(36, io.SEEK_CUR)

            data = f.read(data_length)
            sample_width_in_bytes = 1

            if modes & Mode.SIXTEEN_BIT:
                sample_width_in_bytes = 2
                buf = bytearray(data_length)

                if modes & Mode.UNSIGNED:
                    ii = 0
                    if modes & Mode.UNSIGNED:
                        for word in struct.iter_unpack('<H', data):
                            short = word[0] - 0x8000
                            struct.pack_into('<h', buf, ii, short)
                            ii += 2
                    data = buf
                else:
                    ii = 0
                    for word in struct.iter_unpack('<h', data):
                        struct.pack_into('<h', buf, ii, word[0])
                        ii += 2
                    data = buf

            result.samples.append(Audio(data, sample_width_in_bytes))

            print({
                'fractions': fractions,
                'data_length': data_length,
                'loop_start': loop_start,
                'loop_end': loop_end,
                'sample_rate': sample_rate,
                'low_freq': low_freq,
                'high_freq': high_freq,
                'root_freq': root_freq,
                'stereo_balance': stereo_balance,
                'tremolo_sweep': tremolo_sweep,
                'tremolo_rate': tremolo_rate,
                'tremolo_depth': tremolo_depth,
                'vibrato_sweep': vibrato_sweep,
                'vibrato_rate': vibrato_rate,
                'vibrato_depth': vibrato_depth,
                'modes': modes,
                'scale_freq': scale_freq,
                'scale_factor': scale_factor,
            })

            #
            # timidity:
            #
            # seashore.pat in the Midia patch set has no Sustain.  I don't
            # understand why, and fixing it by adding the Sustain flag to
            # all looped patches probably breaks something else .  We do it
            # anyway.
            #
            # if modes & Mode.LOOPING:
            #     modes |= Mode.SUSTAIN

            #
            # TODO: consult lines starting from 826 in
            # https://github.com/geofft/timidity/blob/a47ff2fcc7eb58ccfda855c00bd57374efa257fa/timidity/instrum.c
            #

            # anyway,

            # data_length <<= FRACTION_BITS
            # loop_start <<= FRACTION_BITS
            # loop_end <<= FRACTION_BITS

            # timidity: adjust for fractional loop points. This is a guess.
            # Does anyone know what "fractions" really stands for?
            # loop_start |= (fractions & 0x0F) << (FRACTION_BITS - 4)
            # loop_end |= ((fractions >> 4) & 0x0F) << (FRACTION_BITS - 4)

    return result
