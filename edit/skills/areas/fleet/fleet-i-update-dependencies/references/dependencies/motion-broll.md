## Motion B-roll project runtime

`motion-broll-project-runtime` belongs to `$video-i-motion-broll`. Node, Python, ffmpeg, and ffprobe come from the declared `node24`, `python`, and `ffmpeg` packages. ffmpeg must include `prores_ks` for transparent ProRes 4444 output.

Load the skill and resolve its folder before running its `./scripts/setup.sh` against the project's `./motion` folder. Setup installs NumPy with pip into `./motion/.venv`, Playwright with npm into `./motion/node_modules`, and Chromium with the local Playwright CLI into its browser cache. It preserves existing project package metadata and records npm resolution in the project's lockfile. Python tools use `./motion/.venv/bin/python`.

This runtime is selected per video project. Fleet distributes the skill without creating a video workspace or installing these libraries globally. The registry verification command checks the environment from the project root. For the full check, run `bash "$SKILL/scripts/setup.sh" --verify ./motion` from the project root to check prerequisites, NumPy, Playwright, and Chromium without installing packages.

To update a project's runtime, use its virtual environment's pip and its local npm package manager, then reinstall Chromium with its local Playwright CLI and run verification. Removal needs an explicit request; scope it to that project's environment and package dependency. Do not remove a shared browser cache as part of project cleanup.
