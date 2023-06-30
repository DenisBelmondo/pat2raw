#!/usr/bin/env python3

# also consult
# http://www33146ue.sakura.ne.jp/staff/iz/formats/guspat.html

import argparse
import io
import sys
import patreader


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=sys.argv[0],
        description='Converts Gravis .PAT files to raw PCM data.')
    parser.add_argument('filename', help='Path to a Gravis .PAT file.', type=str, action='store')

    if len(sys.argv) <= 1:
        parser.print_help()
        return

    args = parser.parse_args()
    result = patreader.read(args.filename)

    if result.error != patreader.Error.OK:
        print('Error: ' + result.error_msg)
        sys.exit(result.error)

    for i in range(len(result.samples)):
        out_path = f'rawpcm{i}'
        with io.open(out_path, 'wb') as outf:
            print(f'Writing raw PCM data to {out_path}.')
            outf.write(result.samples[i].pcm_data)


if __name__ == '__main__':
    main()
