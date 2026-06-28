// t3_styleeditor_layout.cpp
//
// Targeted ASan regression test for PR #519 — StyleEditor layout leak fix.
//
//   sources/editor/styleeditor.cpp
//   -   auto grid_layout = new QGridLayout(this);
//   +   auto grid_layout = new QGridLayout();
//
// Mechanism: `new QGridLayout(this)` immediately installs grid_layout as the
// widget's layout (QLayout ctor calls QWidget::setLayout). The later
// `setLayout(main_layout)` then sees a layout is already installed, prints
// "QWidget::setLayout: Attempting to set QLayout ... which already has a
// layout" and returns WITHOUT taking ownership of main_layout — orphaning the
// whole main_layout/grid_layout tree (leak), once per StyleEditor (Arc, Line,
// Ellipse, Polygon, Rectangle editors).
//
// The patch creates grid_layout parentless; main_layout->addItem(grid_layout)
// takes ownership, and setLayout(main_layout) installs the whole tree under
// the widget.
//
// LEGACY  (new QGridLayout(this)) -> ASan reports the orphaned layout tree.
// PATCHED (new QGridLayout())     -> no leak, single clean owner, no double-free.

#include <QApplication>
#include <QWidget>
#include <QVBoxLayout>
#include <QGridLayout>
#include <QLabel>
#include <QComboBox>
#include <cstdio>

struct StyleEditorLike : QWidget {  // mirrors StyleEditor's layout setup
	StyleEditorLike() {
		auto outline_color = new QComboBox();
		auto filling_color = new QComboBox();

		auto main_layout = new QVBoxLayout();
		main_layout->setContentsMargins(0, 0, 0, 0);
		main_layout->addWidget(new QLabel("Apparence"));

#ifdef LEGACY
		auto grid_layout = new QGridLayout(this);   // pre-patch: self-installs
#else
		auto grid_layout = new QGridLayout();        // patch: parentless
#endif
		grid_layout->addWidget(new QLabel("Contour"), 0, 0);
		grid_layout->addWidget(outline_color, 0, 1);
		grid_layout->addWidget(new QLabel("Remplissage"), 1, 0);
		grid_layout->addWidget(filling_color, 1, 1);
		main_layout->addItem(grid_layout);

		main_layout->addWidget(new QLabel("Geometrie"));
		setLayout(main_layout);     // LEGACY: silently fails -> tree orphaned
	}
};

int main(int argc, char **argv)
{
	QApplication app(argc, argv);
	// Five editors, like opening Arc/Line/Ellipse/Polygon/Rectangle editors.
	for (int i = 0; i < 5; ++i) {
		StyleEditorLike *e = new StyleEditorLike();
		delete e;
	}
	std::printf("t3: 5 StyleEditor-like build/destroy cycles completed\n");
	return 0;
}
