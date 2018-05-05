import asyncio
import subprocess


class SimplePreview:
    def __init__(self, factorio_binary):
        self.binary = factorio_binary
        self.lock = asyncio.Lock()

    async def __call__(self, map_gen_settings_path, image_path, log_path):
        with await self.lock:
            with open(log_path, 'w') as log_file:
                process = await asyncio.create_subprocess_exec(
                    self.binary,
                    '--generate-map-preview', image_path,
                    '--map-gen-settings', map_gen_settings_path,
                    stdout=log_file, stderr=subprocess.STDOUT
                )
                # TODO use wait_for with timeout
            await process.wait()
