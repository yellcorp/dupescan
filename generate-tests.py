#!/usr/bin/env python3

import os
import shutil
import sys


def write_files(source, target_dir, template, num_copies):
    master_path = os.path.join(target_dir, template.format(0))

    print("Writing {}".format(master_path))
    with open(master_path, "wb") as out_stream:
        out_stream.write(source)

    for n in range(1, num_copies):
        copy_path = os.path.join(target_dir, template.format(n))
        print("Copying to {}".format(copy_path))
        shutil.copy(master_path, copy_path)


BIG_SIZE = 0x100005
SMALL_SIZE = 0x2003


def main():
    target_dir = sys.argv[1]
    os.makedirs(target_dir, exist_ok=True)

    buf = bytearray(b"A" * BIG_SIZE)
    write_files(buf, target_dir, "all_a_{}", 5)

    # change a value in the middle to ensure dupes aren't re-unified when
    # identical blocks follow differing blocks
    buf[BIG_SIZE >> 1] ^= 0x0F
    write_files(buf, target_dir, "diff_middle_{}", 5)

    # have one file that differs earlier, splitting it off into its own group
    # of 1 (and therefore not a dupe set)
    buf[BIG_SIZE >> 2] ^= 0x0F
    write_files(buf, target_dir, "diff_singleton_{}", 1)
    buf[BIG_SIZE >> 2] ^= 0x0F
    buf[BIG_SIZE >> 1] ^= 0x0F

    # now at the end. this will test the algorithm to keep the files open
    # as long as possible
    buf[-1] ^= 0x0F
    write_files(buf, target_dir, "diff_end_{}", 5)
    buf[-1] ^= 0x0F

    # now at the start
    buf[0] ^= 0x0F
    write_files(buf, target_dir, "diff_start_{}", 5)
    buf[0] ^= 0x0F

    # sanity (?) something the same size but all different
    buf = bytearray(b"B" * BIG_SIZE)
    write_files(buf, target_dir, "all_b_{}", 5)

    # smaller files, but stress the number that we have open at once
    buf = bytearray(b"A" * SMALL_SIZE)
    write_files(buf, target_dir, "open_stress_a_{}", 320)

    buf[-512] ^= 0x0F
    write_files(buf, target_dir, "open_stress_b_{}", 260)

    # some zero files
    write_files(b"", target_dir, "zero_{}", 5)


if __name__ == "__main__":
    main()
