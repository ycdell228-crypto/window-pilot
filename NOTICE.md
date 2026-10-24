# References and licensing status

Window Pilot is licensed under the MIT License. See [LICENSE](LICENSE). Third-party references and dependency licenses remain as described below.

Reference reviewed:

- [dev-willbird1936/Desktop-Computer-Use](https://github.com/dev-willbird1936/Desktop-Computer-Use), commit `2bc83f552246dc3909c81f08b3b59bda9963e4b2`, MIT, copyright (c) 2026 dev-willbird1936.
- Reviewed `ScreenshotService.cs` and `BackgroundInput.cs` for HWND capture, occlusion, error/timeout behavior and focus caveats. Window Pilot is a separate Python implementation and does not ship the reference repository or its release executable. Its optional screen/foreground paths are not exposed here.
- [Microsoft PrintWindow documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-printwindow) and [PostMessageW documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-postmessagew).
- DSH 0.2.1-rc.2 installed module documentation and source for `@deepseek-ai/dsh-mcp-client` and `dsh-app-boot` were inspected to establish the MCP configuration contract. No DSH source or binary is redistributed.

The PrintWindow base path uses the Python standard library. The optional HWND-only WGC backend uses [PyWinRT](https://github.com/pywinrt/pywinrt), and bounded MCP image previews use [Pillow](https://github.com/python-pillow/Pillow). Pinned optional packages are listed in requirements-wgc.txt and installed separately; this source tree does not redistribute their binary wheels. Their own licenses remain applicable and do not select a license for Window Pilot. Preserve applicable notices if dependencies are redistributed later.
