/*
    Drive EdzImporter::importToDirectory() against every file in a corpus
    directory and report the outcome.  Run under ASAN to catch memory errors.

    Usage:  fuzz_edz [corpus-dir]   (default: ./corpus)
*/
#include "edzimporter.h"

#include <QCoreApplication>
#include <QDir>
#include <QDirIterator>
#include <QTemporaryDir>

#include <cstdio>

int main(int argc, char *argv[])
{
    QCoreApplication app(argc, argv);

    const QString corpus = argc > 1
        ? QString::fromUtf8(argv[1])
        : QStringLiteral("corpus");

    if (!QDir(corpus).exists()) {
        fprintf(stderr, "Corpus directory not found: %s\n", qPrintable(corpus));
        return 1;
    }

    QTemporaryDir out;
    if (!out.isValid()) {
        fprintf(stderr, "Cannot create temporary output directory\n");
        return 1;
    }

    int n_ok = 0, n_err = 0;

    QDirIterator it(corpus, QDir::Files, QDirIterator::Subdirectories);
    while (it.hasNext()) {
        it.next();
        const QString name = it.fileName();
        const QString path = it.filePath();

        EdzImporter importer;
        const bool ok = importer.importToDirectory(path, out.path());

        printf("%-55s  %s%s\n",
               qPrintable(name),
               ok ? "OK " : "ERR",
               ok ? "" : qPrintable(QStringLiteral("  ") + importer.errorString()));
        fflush(stdout);

        ok ? ++n_ok : ++n_err;
    }

    printf("\n%d ok, %d errors (errors are expected for malformed inputs)\n",
           n_ok, n_err);
    return 0;
}
