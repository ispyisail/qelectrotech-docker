// t1_exportdialog_qdeleteall.cpp
//
// Targeted ASan regression test for PR #519 — ExportDialog leak fix.
//
//   sources/exportdialog.cpp
//   ~ExportDialog() { qDeleteAll(diagram_lines_); }
//
// PLC-user's concern (PR review, sources/exportdialog.cpp:115):
//   "qDeleteAll() leaves the container populated with dangling (freed)
//    pointers. You must explicitly call .clear() on the container afterward
//    to avoid crashes... It seems that we also need diagram_lines_.clear();"
//
// This test reproduces the EXACT ownership pattern of ExportDialog /
// ExportDiagramLine:
//   - The dialog owns  QHash<int, Line*> lines_  (mirrors diagram_lines_).
//   - Each Line heap-allocates child QWidgets which are added to a layout and
//     thereby REPARENTED to a container widget owned by the dialog. So the
//     widgets are owned by Qt's parent-child chain, NOT by Line.
//   - ~Line() is empty — exactly like ~ExportDiagramLine().
//   - ~Dialog() calls qDeleteAll(lines_) with NO subsequent .clear().
//
// Build LEGACY (no qDeleteAll)  -> ASan must report the leaked Line structs.
// Build PATCHED (qDeleteAll)    -> ASan must report ZERO direct leaks and,
//                                  crucially, NO use-after-free / double-free.
//
// Why .clear() is unnecessary here: qDeleteAll is the LAST statement of the
// destructor. The QHash member is destroyed immediately afterwards by the
// implicit member-dtor, freeing only the hash's internal node storage — it
// never dereferences the (now dangling) Line* values. No code path can touch
// lines_ after ~Dialog() returns. The Qt-docs warning about .clear() applies
// to containers that are *reused* after qDeleteAll, not to a destructor.

#include <QApplication>
#include <QWidget>
#include <QVBoxLayout>
#include <QCheckBox>
#include <QLabel>
#include <QLineEdit>
#include <QHash>
#include <cstdio>

struct Line {                       // mirrors ExportDialog::ExportDiagramLine
	QCheckBox *must_export;
	QLabel    *title_label;
	QLineEdit *file_name;
	Line(QVBoxLayout *layout) {
		// Created parentless, then reparented to the layout's parent
		// widget by addWidget() — exactly as ExportDiagramLine does.
		must_export = new QCheckBox();
		title_label = new QLabel("folio");
		file_name   = new QLineEdit();
		layout->addWidget(must_export);
		layout->addWidget(title_label);
		layout->addWidget(file_name);
	}
	~Line() {}                      // empty, like ~ExportDiagramLine()
};

struct Dialog : QWidget {           // mirrors ExportDialog
	QHash<int, Line*> lines_;       // mirrors diagram_lines_
	Dialog() {
		auto *container = new QWidget(this);      // owned by the dialog
		auto *layout = new QVBoxLayout(container);
		for (int i = 0; i < 8; ++i)
			lines_.insert(i, new Line(layout));
	}
	~Dialog() override {
#ifndef LEGACY
		qDeleteAll(lines_);         // <-- the patch under test (no .clear())
#endif
		// LEGACY build omits the line entirely: Line structs leak.
	}
};

int main(int argc, char **argv)
{
	QApplication app(argc, argv);
	// Several build/destroy cycles: if qDeleteAll left anything in a state
	// that a later destruction touched, ASan would fire on a subsequent round.
	for (int round = 0; round < 5; ++round) {
		Dialog *d = new Dialog();
		delete d;   // ~Dialog body (qDeleteAll) runs first, then ~QWidget
		            // deletes the child widgets. Order guarantees no UAF.
	}
	std::printf("t1: 5 ExportDialog build/destroy cycles completed cleanly\n");
	return 0;
}
