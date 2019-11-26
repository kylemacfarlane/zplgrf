import warnings

from .base import RasterLabel, RasterLabelCollection, RasterLabelException


class BrotherRasterLabel(RasterLabel):
    @classmethod
    def extract_printer_rasters(
        cls, data, skip_undocumented_commands={0x55: 15}
    ):
        rasters = []
        current_raster = []
        num_raster_lines = 0
        expected_num_raster_lines = 0
        compressed = True  # Compression is on by default?
        high_res = False
        i = 0

        while i < len(data):
            b = data[i]
            if b in (0x47, 0x67):
                # Raster line
                # 0x67 is untested but the byteorder appears to be the only
                # documented difference
                num_bytes = int.from_bytes(
                    data[i+1:i+3],
                    byteorder='big' if b == 0x67 else 'little'
                )
                line_data = data[i+3:i+3+num_bytes]
                i += num_bytes + 2

                if not compressed:
                    current_raster.append(line_data)
                else:
                    line = []
                    repeat = 0
                    for b2 in line_data:
                        if repeat < 0:
                            line += [b2] * -repeat
                            repeat = 0
                        elif repeat > 0:
                            line.append(b2)
                            repeat -= 1
                        elif b2 < 128:
                            repeat = b2 + 1
                        elif b2 >= 128:
                            repeat = b2 - 256 - 1
                    current_raster.append(bytes(line))
            elif b == 0x5A and current_raster:
                # Blank raster line
                current_raster.append(bytes(
                    [0] * len(current_raster[0])
                ))
            elif b in (0x0C, 0x1A) and current_raster:
                # Print page / Print page with feeding
                num_raster_lines += len(current_raster)
                current_raster.reverse()
                if high_res:
                    # High res rasters have double the rows which results in a
                    # stretched image unless we also double the columns
                    if high_res:
                        stretched_raster = []
                        for row in current_raster:
                            stretched_row = []
                            for b in row:
                                b = format(b, '08b')
                                b = ''.join([c for c in b for _ in (0, 1)])
                                stretched_row.append(bytes(
                                    [int(b[:8], 2), int(b[8:], 2)]
                                ))
                            stretched_raster.append(b''.join(stretched_row))
                        current_raster = stretched_raster
                rasters.append(
                    cls.from_bytes(
                        b''.join(current_raster), len(current_raster[0])
                    )
                )
                current_raster = []
            elif b == 0x4D:
                # Compression mode
                compressed = data[i+1] == 0x02
                i += 1
            elif b == 0x00:
                # Invalidate
                i += 99
            elif b == 0x1B:
                # Unfortunately because of varying argument lengths we have
                # to handle every command rather than blindly skipping ahead
                if data[i+1] == 0x40:
                    # Initialise
                    i += 1
                elif data[i+1] == 0x69:
                    cmd = data[i+2]
                    i += 2
                    if cmd in (
                        0x21,  # Switch automatic status notification mode
                        0x41,  # Specify the page number in "cut each * labels"
                        0x4D,  # Various mode settings
                        0x53  # Status information request
                    ):
                        i += 1
                    elif cmd == 0x4B:
                        # Advanced mode settings
                        high_res = format(data[i+1], '08b')[1] == '1'
                        i += 1
                    elif cmd == 0x61:
                        # Switch dynamic command mode
                        # 0x00 = ESC/P
                        # 0x01 = Raster
                        # 0x02 = P-Touch Template
                        if data[i+1] != 0x01:
                            raise RasterLabelException(
                                'Encountered non-raster mode'
                            )
                        i += 1
                    elif cmd == 0x64:
                        # Specify margin amount (feed amount)
                        i += 2
                    elif cmd == 0x7A:
                        # Print information command
                        expected_num_raster_lines += (
                            int.from_bytes(data[i+5:i+9], byteorder='little')
                        )
                        i += 10
                    else:
                        # Undocumented commands
                        if cmd in skip_undocumented_commands:
                            # Known undocumented commands
                            i += skip_undocumented_commands[cmd]
                        else:
                            # Unknown undocumented commands, skip and hope for
                            # the best
                            i += 1
                            warnings.warn(
                                'Encountered undocumented command: %s' %
                                hex(cmd)
                            )

            i += 1

        # Since it's apparently OK to send rasters with no additional commands
        # over the network then we should only check this the number of lines
        # if it's present
        if (
            expected_num_raster_lines and
            num_raster_lines != expected_num_raster_lines
        ):
            raise RasterLabelException('Number of raster lines does not match')

        return RasterLabelCollection(rasters)

    def to_printer_raster(
        self,
        compression=True,
        printer_bytes_width=16,
        raster_command=0x47
    ):
        # 0x67 is untested but the byteorder appears to be the only
        # documented difference
        byteorder = 'big' if raster_command == 0x67 else 'little'

        rows = []

        for row in self.bytes_rows:
            if len(row) < printer_bytes_width:
                # If it's too narrow pad it into the middle
                diff = printer_bytes_width - len(row)
                left = diff // 2
                right = diff - left
                row = (
                    bytes([0x00] * left) +
                    row +
                    bytes([0x00] * right)
                )
            elif len(row) > printer_bytes_width:
                # If it's too wide crop off the sides
                diff = len(row) - printer_bytes_width
                left = diff // 2
                right = diff - left
                row = row[left:-right]

            if not compression:
                rows.append(
                    bytes([raster_command]) +
                    printer_bytes_width.to_bytes(2, byteorder=byteorder) +
                    row
                )
                continue

            if all(b == 0x00 for b in row):
                rows.append(bytes([0x5A]))
                continue

            i = 0
            compressed_row = []
            while i < len(row):
                start_i = i
                while i+1 < len(row) and row[i] == row[i+1]:
                    i += 1
                if i - start_i > 0:
                    # Repeating
                    chunk = row[start_i:i+1]
                    count = abs(len(chunk) - 1 - 256)
                    chunk = bytes([chunk[0]])
                else:
                    # Non-repeating
                    while (
                        i+2 < len(row) and
                        row[i+1] != row[i+2]
                    ):
                        i += 1
                    chunk = row[start_i:i+1]
                    count = len(chunk) - 1
                compressed_row.append(bytes([count]) + chunk)
                i += 1

            compressed_row = b''.join(compressed_row)
            rows.append(
                bytes([raster_command]) +
                len(compressed_row).to_bytes(2, byteorder=byteorder) +
                compressed_row
            )

        rows.reverse()

        if compression and rows[0] == bytes([0x5A]):
            # If the first line is a zero raster line then the official Windows
            # driver replaces it with a line compressed like this. This is most
            # likely done to allow us to detect the width.
            rows[0] = bytes([
                raster_command, 0x02, 0x00,
                0xFF - (printer_bytes_width - 2), 0x00
            ])

        return {
            'compression': compression,
            'data': b''.join(rows),
            'num_lines': len(rows)
        }


class SimpleBrotherPrinter:
    """
    A very simple class to wrap up the rasters in enough commands to test them
    on a real printer.

    If you need more options you should create your own class. Do not open
    issues or pull requests trying to expand this class into a full blown
    printer driver.

    The diagrams in the documentation imply that you only need to send the
    raster over the network but other commands may be required over USB. They
    also show that you should send jobs in chunks but sending it all at once
    seems to work OK.
    """
    @staticmethod
    def print(
        rasters,
        auto_cut=True,
        chain_printing=False,
        draft=False,
        half_cut=True,
        media_width=None,
        mirror_printing=False,
        no_buffer_clearing=False,
        special_tape=False
    ):
        output = [
            bytes([0x00] * 100),  # Invalidate
            bytes([0x1B, 0x40])  # Initialise
        ]

        # The print information command will cause my printer to error if the
        # media width and and type don't match what's loaded. So it seems
        # better to not send the command and let the printer auto-detect but
        # it appears to be necessary when compression is off otherwise my
        # printer outputs a blank label.
        if any(not r['compression'] for r in rasters):
            if media_width is None:
                raise RasterLabelException(
                    'Media width is required for uncompressed rasters'
                )
            num_lines = sum(r['num_lines'] for r in rasters)
            # Note that some media widths don't use the same number as the
            # real size in mm. Check the developer manual for your printer.
            print_information = (
                bytes([0x1B, 0x69, 0x7A, 0x84, 0x00, media_width, 0x00]) +
                num_lines.to_bytes(4, byteorder='little') +
                bytes([0x00, 0x00])
            )
            output.append(print_information)

        for i, raster in enumerate(rasters, 1):
            various_mode_settings = int(''.join([
                '1' if mirror_printing else '0',
                '1' if auto_cut else '0',
                '000000'  # All unused
            ]), 2)
            advanced_mode_settings = int(''.join([
                '1' if no_buffer_clearing else '0',
                '0',  # High resolution printing, not implemented because it
                      # doesn't work on my printer so I can't test it
                '0',  # Unused
                '1' if special_tape else '0',
                '0' if chain_printing else '1',
                '1' if half_cut else '0',
                '0',  # Unused
                '1' if draft else '0'
            ]), 2)
            output += [
                bytes([0x1B, 0x69, 0x61, 0x01]),  # Raster mode
                bytes([0x1B, 0x69, 0x4D, various_mode_settings]),
                bytes([0x1B, 0x69, 0x4B, advanced_mode_settings]),
                bytes([0x4D, 0x02 if raster['compression'] else 0x00]),
                raster['data'],
                bytes([0x1A if i == len(rasters) else 0x0C])  # Print
            ]

        return b''.join(output)
