// IOP setup shared by the test ELFs: USB mass storage (mass0:), pad, memory cards, sound (audsrv on libsd).
// Sequence as in pcm720/nhddl src/module_init.c:70-192 @821b6c9 (reference only, see docs/sources.md):
// IOP reset -> RPC -> sbv patches (load modules from EE RAM) -> iomanX, fileXio (+fileXioInit), sio2man,
// mcman, mcserv (after sio2man: ps2sdk libmc.h), freepad, libsd, audsrv (libsd first: ps2sdk audsrv playadpcm.c),
// bdm, bdmfs_fatfs, usbd_mini, usbmass_bd_mini; then poll mass0: while the stick mounts.
#include <dirent.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <iopcontrol.h>
#include <loadfile.h>
#include <sbv_patches.h>
#include <sifrpc.h>
#include <libpad.h>
#define NEWLIB_PORT_AWARE // only fileXioInit() is used; file I/O goes through stdio (fileXio_rpc.h guard)
#include <fileXio_rpc.h>
#include "iop.h"

#define IRX(m) extern unsigned char m##_irx[]; extern unsigned int size_##m##_irx
IRX(iomanX); IRX(fileXio); IRX(sio2man); IRX(mcman); IRX(mcserv); IRX(freepad); IRX(libsd); IRX(audsrv); IRX(bdm); IRX(bdmfs_fatfs); IRX(usbd_mini); IRX(usbmass_bd_mini);

// Each open port needs its own 256-byte, 64-byte-aligned DMA region.
static unsigned char pad_buf[2][256] __attribute__((aligned(64)));
static volatile int pad_open[2];
static int pad_mode_tried[2];
static int pad_state[2] = {-1, -1};
static int pad_valid[2];

static void pads_init(void)
{
    if (padInit(0) != 1) {
        printf("pad: libpad initialization failed\n");
        return;
    }
    for (int port = 0; port < 2; port++) {
        pad_open[port] = padPortOpen(port, 0, pad_buf[port]) != 0;
        printf("pad: port %d open=%d\n", port + 1, pad_open[port]);
    }
}

int iop_load(void)
{
	while (!SifIopReset("", 0)) {}
	while (!SifIopSync()) {}
	SifInitRpc(0);
	sbv_patch_enable_lmb();
	sbv_patch_disable_prefix_check();
	struct { unsigned char *irx; unsigned int *size; } mods[] = {
		{iomanX_irx, &size_iomanX_irx}, {fileXio_irx, &size_fileXio_irx}, {sio2man_irx, &size_sio2man_irx},
		{mcman_irx, &size_mcman_irx}, {mcserv_irx, &size_mcserv_irx},
		{freepad_irx, &size_freepad_irx}, {libsd_irx, &size_libsd_irx}, {audsrv_irx, &size_audsrv_irx},
		{bdm_irx, &size_bdm_irx}, {bdmfs_fatfs_irx, &size_bdmfs_fatfs_irx},
		{usbd_mini_irx, &size_usbd_mini_irx}, {usbmass_bd_mini_irx, &size_usbmass_bd_mini_irx}};
	for (unsigned i = 0; i < sizeof(mods) / sizeof(mods[0]); i++) {
		int iopret = 0;
		if (SifExecModuleBuffer(mods[i].irx, *mods[i].size, 0, NULL, &iopret) < 0 || iopret == 1)
			return 0;
		if (mods[i].irx == fileXio_irx)
			fileXioInit();
	}
	pads_init();
	return 1;
}

int usb_wait(void)
{
	for (int attempt = 0; attempt < 10; attempt++) { // nhddl src/devices_bdm.c:100-115
		DIR *d = opendir("mass0:/");
		if (d) { closedir(d); return 1; }
		sleep(1);
	}
	return 0;
}

int iop_init(void) { return iop_load() && usb_wait(); }

// Do not busy-wait for a disconnected pad: the UI must keep rendering and permit hot-plugging.
unsigned pad_buttons(void)
{
    unsigned buttons = 0;
    for (int port = 0; port < 2; port++) {
        pad_valid[port] = 0;
        if (!pad_open[port]) continue;
        int state = padGetState(port, 0);
        if (state != pad_state[port]) {
            printf("pad: port %d state=%d\n", port + 1, state);
            pad_state[port] = state;
        }
        if (state == PAD_STATE_DISCONN || state == PAD_STATE_ERROR) {
            pad_mode_tried[port] = 0;
            continue;
        }
        if (state != PAD_STATE_STABLE && state != PAD_STATE_FINDCTP1) continue;
        // Only ask for analog mode when the controller advertises it. No pressure or vibration commands:
        // digital pads and clones remain usable; unlocked mode lets the ANALOG button keep working.
        if (!pad_mode_tried[port] && state == PAD_STATE_STABLE) {
            pad_mode_tried[port] = 1;
            int count = padInfoMode(port, 0, PAD_MODETABLE, -1);
            for (int mode = 0; mode < count && mode < 8; mode++) {
                if (padInfoMode(port, 0, PAD_MODETABLE, mode) == PAD_TYPE_DUALSHOCK) {
                    if (padSetMainMode(port, 0, PAD_MMODE_DUALSHOCK, PAD_MMODE_UNLOCK))
                        goto next_port; // asynchronous command: wait until a later frame to read
                    break; // rejected command: keep the controller's current mode
                }
            }
        }
        struct padButtonStatus data;
        memset(&data, 0, sizeof(data));
        int len = padRead(port, 0, &data);
        // libpad returns a packet length, not a boolean. Incomplete/stale packets are not button states.
        if (len < 4 || data.ok != 0 || (data.mode >> 4) < 4) continue;
        unsigned held = (0xffff ^ data.btns) & 0xffff;
        if (len >= 8 && ((data.mode >> 4) == PAD_TYPE_DUALSHOCK || (data.mode >> 4) == PAD_TYPE_ANALOG)) {
            if (data.ljoy_h < 64) held |= PAD_LEFT;
            if (data.ljoy_h > 192) held |= PAD_RIGHT;
            if (data.ljoy_v < 64) held |= PAD_UP;
            if (data.ljoy_v > 192) held |= PAD_DOWN;
        }
        buttons |= held;
        pad_valid[port] = 1;
next_port:;
    }
    return buttons;
}

int pad_connected(void) { return pad_valid[0] || pad_valid[1]; }
int pad_port_state(int port) { return port >= 0 && port < 2 ? pad_state[port] : -1; }
