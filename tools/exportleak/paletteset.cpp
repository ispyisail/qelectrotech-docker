// paletteset.cpp — LD_PRELOAD shim that forces a QApplication palette for a
// headless QET export, without touching QET source.
//
// QET's export path (sources/main.cpp) constructs a QApplication and then
// renders straight away; it never calls setPalette, so on the offscreen
// platform every run gets Qt's default (light) palette. The exportleak
// light-vs-dark sweep needs the *same* binary run under two palettes. This
// library interposes the QApplication complete-object constructor (the one
// `QApplication export_app(argc, argv)` compiles to), runs the real
// constructor, then applies a dark palette when QET_EXPORT_PALETTE=dark is
// set in the environment. Unset (or anything other than "dark") leaves the
// Qt default untouched, so the light run and dark run share one code path.
//
// The symbol is versioned Qt_5 via the accompanying version script so it
// satisfies the qelectrotech binary's versioned relocation
// (_ZN12QApplicationC1ERiPPci@Qt_5) and interposes cleanly.
#include <QApplication>
#include <QPalette>
#include <QColor>

#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <dlfcn.h>

// QApplication::QApplication(int &argc, char **argv, int = ApplicationFlags)
//   Itanium ABI C1 (complete object) ctor; `int &` is passed as `int *`.
using QAppCtor = void (*)(QApplication *, int *, char **, int);

extern "C" void _ZN12QApplicationC1ERiPPci(QApplication *self, int *argc,
                                           char **argv, int flags);

static void applyDarkPalette()
{
    const char *mode = std::getenv("QET_EXPORT_PALETTE");
    if (!mode || std::strcmp(mode, "dark") != 0) {
        return;
    }

    // A representative dark palette. The role that actually leaks into an
    // export is QPalette::Text: QGraphicsTextItem falls back to
    // QApplication::palette().color(QPalette::Text) when its default text
    // colour was never set (the #247 cross-reference-text bug). The rest are
    // set for completeness so any other palette read is equally visible.
    QPalette p = QApplication::palette();
    p.setColor(QPalette::Window,          QColor("#2d2d2d"));
    p.setColor(QPalette::WindowText,      QColor("#ffffff"));
    p.setColor(QPalette::Base,            QColor("#1e1e1e"));
    p.setColor(QPalette::AlternateBase,   QColor("#353535"));
    p.setColor(QPalette::Text,            QColor("#ffffff"));
    p.setColor(QPalette::Button,          QColor("#353535"));
    p.setColor(QPalette::ButtonText,      QColor("#ffffff"));
    p.setColor(QPalette::BrightText,      QColor("#ffffff"));
    p.setColor(QPalette::Highlight,       QColor("#2a82da"));
    p.setColor(QPalette::HighlightedText, QColor("#ffffff"));
    p.setColor(QPalette::ToolTipBase,     QColor("#2d2d2d"));
    p.setColor(QPalette::ToolTipText,     QColor("#ffffff"));
    QApplication::setPalette(p);
}

extern "C" void _ZN12QApplicationC1ERiPPci(QApplication *self, int *argc,
                                           char **argv, int flags)
{
    static QAppCtor real = nullptr;
    if (!real) {
        real = reinterpret_cast<QAppCtor>(
            dlvsym(RTLD_NEXT, "_ZN12QApplicationC1ERiPPci", "Qt_5"));
        if (!real) {
            real = reinterpret_cast<QAppCtor>(
                dlsym(RTLD_NEXT, "_ZN12QApplicationC1ERiPPci"));
        }
        if (!real) {
            std::fprintf(stderr,
                         "paletteset: cannot find real QApplication ctor: %s\n",
                         dlerror());
            std::_Exit(2);
        }
    }
    real(self, argc, argv, flags);
    applyDarkPalette();
}
