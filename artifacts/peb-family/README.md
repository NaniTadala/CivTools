# Grouped PEB frame section

The main tool picker now has one **PEB frames** entry. Frame A, B, C and D are
selected inside that section using a compact row of buttons. The active frame
is highlighted. Hover over a frame for its structural description; each frame
also has a named, expandable geometry preview.

Each frame retains its own inputs. Returning through the picker or a favourite
restores the last frame, including after a restart. Alt+A/B/C/D still select
individual variants directly.

## Screenshots reviewed

- [Grouped section](1/frame-C.png)
- [Main picker with one PEB entry](1/tool-picker.png)
- [Frame A](1/frame-A.png), [B](1/frame-B.png), [C](1/frame-C.png), [D](1/frame-D.png)
- [Geometry preview](1/geometry-preview.png)
- [125% rendering](1.25/frame-C.png)
- [150%, minimum window width](1.5/minimum-width.png)
- [Native Windows capture with Pin enabled](native-1/pinned-native.png)

The render script captures the top and bottom of all four variant forms, the
picker, geometry preview, expanded layout, narrow layout and another tool to
verify that the variant buttons are scoped to PEB. It uses temporary settings
and makes no CAD calls. Button caption checks found no undersized controls in
100%, 125%, 150% or native Windows rendering.

Reproduce with `python artifacts/render_peb_family.py` or add `--native` for a
Windows screen capture. Set QT_SCALE_FACTOR to 1.25 or 1.5 for scaled rendering.
