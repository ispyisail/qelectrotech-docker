/* wmstate — minimal EWMH window-state tool (stand-in for wmctrl, which isn't
 * installed here). Used by guiauto.sh to un-maximize a window so it can be
 * moved to a specific monitor: xfwm4 ignores move/resize on maximized windows.
 *
 *   wmstate <window-id> unmaximize
 *   wmstate <window-id> maximize
 *
 * Sends a _NET_WM_STATE client message to the root window, per EWMH.
 */
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define _NET_WM_STATE_REMOVE 0
#define _NET_WM_STATE_ADD    1

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: wmstate <winid> maximize|unmaximize\n"); return 2; }
    Window win = (Window) strtoul(argv[1], NULL, 0);
    int action = (strcmp(argv[2], "maximize") == 0) ? _NET_WM_STATE_ADD : _NET_WM_STATE_REMOVE;

    Display *d = XOpenDisplay(NULL);
    if (!d) { fprintf(stderr, "cannot open display\n"); return 1; }

    Atom wm_state   = XInternAtom(d, "_NET_WM_STATE", False);
    Atom max_horz   = XInternAtom(d, "_NET_WM_STATE_MAXIMIZED_HORZ", False);
    Atom max_vert   = XInternAtom(d, "_NET_WM_STATE_MAXIMIZED_VERT", False);

    XEvent e; memset(&e, 0, sizeof(e));
    e.xclient.type         = ClientMessage;
    e.xclient.window       = win;
    e.xclient.message_type = wm_state;
    e.xclient.format       = 32;
    e.xclient.data.l[0]    = action;
    e.xclient.data.l[1]    = (long) max_horz;
    e.xclient.data.l[2]    = (long) max_vert;
    e.xclient.data.l[3]    = 1;   /* source: normal application */

    XSendEvent(d, DefaultRootWindow(d), False,
               SubstructureNotifyMask | SubstructureRedirectMask, &e);
    XFlush(d);
    XCloseDisplay(d);
    return 0;
}
