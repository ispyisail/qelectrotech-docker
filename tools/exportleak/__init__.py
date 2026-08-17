"""tools.exportleak -- detect editing-state decoration leaking into exports.

QElectroTech's headless export (sources/cli_export.cpp) writes PDF, PNG and
SVG for every folio of a project. An editing-state visual drawn inside a
QGraphicsItem's paint() (a halo, a highlight, a hover ring) leaks into all
three because they all go through the same QPainter render path.

SVG is the precise detector: it is XML, so a leaked decoration can be found
textually -- by tag, by colour, by partial opacity -- instead of by fragile
image comparison. PNG and PDF are compared coarsely (file size / pixel count)
as a sanity check.

See the X5 brief (briefs/X5-deepseek.md) for the PR #701 rejection this was
built to catch.
"""
