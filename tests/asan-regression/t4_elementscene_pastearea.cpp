// t4_elementscene_pastearea.cpp
//
// Targeted ASan regression test for PR #519 — ElementScene paste-area leak fix.
//
//   sources/editor/elementscene.cpp  (~ElementScene)
//   +   if (m_paste_area && !m_paste_area->scene())
//   +       delete m_paste_area;
//
// m_paste_area (a QGraphicsRectItem) is created in initPasteArea() and is
// added to / removed from the scene during XML paste. At destruction it is
// usually NOT in the scene, so ~QGraphicsScene does not free it -> leak.
//
// The two cases that matter for safety:
//   (A) paste_area NOT in scene at dtor  -> guard true  -> manual delete (fixes
//       the leak). LEGACY (no delete) leaks it.
//   (B) paste_area STILL in scene at dtor -> guard false -> base ~QGraphicsScene
//       deletes it. The `!scene()` guard MUST prevent a manual delete here,
//       otherwise double-free. This test exercises (B) explicitly to prove the
//       guard avoids a double-free.
//
// LEGACY  -> case (A) leaks the rect item.
// PATCHED -> case (A) clean, case (B) no double-free.

#include <QApplication>
#include <QGraphicsScene>
#include <QGraphicsRectItem>
#include <cstdio>

class SceneLike : public QGraphicsScene {   // mirrors ElementScene
	QGraphicsRectItem *m_paste_area = nullptr;
	bool keep_in_scene_;
public:
	explicit SceneLike(bool keep_in_scene) : keep_in_scene_(keep_in_scene) {
		m_paste_area = new QGraphicsRectItem();   // initPasteArea(): parentless
		m_paste_area->setZValue(1000000);
		// Simulate the add/remove dance of a paste operation.
		addItem(m_paste_area);
		if (!keep_in_scene_)
			removeItem(m_paste_area);             // normal end-state: removed
	}
	~SceneLike() override {
#ifndef LEGACY
		if (m_paste_area && !m_paste_area->scene())   // <-- the patch
			delete m_paste_area;
#endif
		// LEGACY: nothing -> case (A) leaks m_paste_area.
	}
};

int main(int argc, char **argv)
{
	QApplication app(argc, argv);   // QGraphicsScene::addItem touches qApp
	// Case (A): paste_area removed before dtor (the common case the leak fix
	// targets). PATCHED frees it; LEGACY leaks it.
	for (int i = 0; i < 5; ++i) {
		SceneLike *s = new SceneLike(/*keep_in_scene=*/false);
		delete s;
	}

	// Case (B): paste_area still in the scene at dtor. base ~QGraphicsScene
	// frees it; the guard must NOT also delete it (else double-free -> ASan).
	for (int i = 0; i < 5; ++i) {
		SceneLike *s = new SceneLike(/*keep_in_scene=*/true);
		delete s;
	}

	std::printf("t4: paste-area case A (removed) + case B (in-scene) completed\n");
	return 0;
}
