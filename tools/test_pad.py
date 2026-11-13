#!/usr/bin/env python3
"""Host regression tests for the actual pad routines extracted from iop.c (no PS2 SDK required)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = (root / 'iop.c').read_text()
setup = source[source.index('// Each open port'):source.index('int iop_load(void)')]
reader = source[source.index('unsigned pad_buttons(void)'):]
mock = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define PAD_STATE_DISCONN 0
#define PAD_STATE_FINDCTP1 2
#define PAD_STATE_EXECCMD 5
#define PAD_STATE_STABLE 6
#define PAD_STATE_ERROR 7
#define PAD_TYPE_DUALSHOCK 7
#define PAD_TYPE_ANALOG 5
#define PAD_MODETABLE 4
#define PAD_MMODE_DUALSHOCK 1
#define PAD_MMODE_UNLOCK 2
#define PAD_LEFT 128
#define PAD_RIGHT 32
#define PAD_UP 16
#define PAD_DOWN 64
struct padButtonStatus { unsigned char ok, mode; unsigned short btns; unsigned char rjoy_h,rjoy_v,ljoy_h,ljoy_v; };
static int states[2], lengths[2], modes[2], request[2], reads[2], sets[2];
static struct padButtonStatus packets[2];
static int padInit(int v) { return v == 0; }
static int padPortOpen(int p,int s,void *area) { assert(s==0 && p<2 && ((unsigned long)area % 64)==0);return 1; }
static int padGetState(int p,int s) { (void)s;return states[p]; }
static int padInfoMode(int p,int s,int mode,int index) { (void)s;assert(mode==PAD_MODETABLE);return index==-1 ? modes[p] : PAD_TYPE_DUALSHOCK; }
static int padSetMainMode(int p,int s,int mode,int lock) { assert(s==0 && mode==1 && lock==2);sets[p]++;return request[p]; }
static int padRead(int p,int s,struct padButtonStatus *out) { (void)s;reads[p]++;*out=packets[p];return lengths[p]; }
'''
tests = r'''
int main(void) {
 pads_init();
 assert(pad_open[0] && pad_open[1]);
 assert((char*)pad_buf[1] - (char*)pad_buf[0] == 256);
 assert(pad_buttons()==0 && reads[0]==0 && !pad_connected());
 states[0]=PAD_STATE_EXECCMD;
 assert(pad_buttons()==0 && reads[0]==0);
 states[0]=PAD_STATE_FINDCTP1;lengths[0]=4;
 packets[0]=(struct padButtonStatus){.mode=0x41,.btns=0xffff ^ 0x4000};
 assert(pad_buttons()==0x4000 && pad_connected()); // digital pad, no analog command required
 states[0]=PAD_STATE_STABLE;lengths[0]=3;
 assert(pad_buttons()==0 && !pad_connected()); // old code treated any nonzero length as valid
 lengths[0]=4;packets[0].ok=0xff;
 assert(pad_buttons()==0);
 packets[0].ok=0;packets[0].mode=0;
 assert(pad_buttons()==0);
 // disconnect/reconnect and a second-port controller remain usable without restart
 states[0]=PAD_STATE_DISCONN;states[1]=PAD_STATE_STABLE;lengths[1]=4;
 packets[1]=(struct padButtonStatus){.mode=0x41,.btns=0xffff ^ 0x20};
 assert(pad_buttons()==0x20 && pad_port_state(0)==0 && pad_port_state(1)==6);
 // advertised DualShock gets exactly one unlocked-mode request per connection
 states[0]=PAD_STATE_STABLE;modes[0]=1;request[0]=1;lengths[0]=8;
 packets[0]=(struct padButtonStatus){.mode=0x73,.btns=0xffff,.ljoy_h=128,.ljoy_v=128};
 assert(pad_buttons()==0x20 && sets[0]==1);
 packets[0].ljoy_h=20;packets[0].ljoy_v=230;
 assert(pad_buttons()==(0x20|PAD_LEFT|PAD_DOWN) && sets[0]==1);
 states[1]=PAD_STATE_ERROR;
 assert(pad_buttons()==(PAD_LEFT|PAD_DOWN));
 states[0]=PAD_STATE_DISCONN;pad_buttons();
 states[0]=PAD_STATE_STABLE;request[0]=0;
 assert(pad_buttons()==(PAD_LEFT|PAD_DOWN) && sets[0]==2); // rejected mode change still reads current mode
 assert(pad_buttons()==(PAD_LEFT|PAD_DOWN) && sets[0]==2);
 puts("pad selftest ok: digital, analog, short/error packets, both ports, reconnect and mode fallback");
}
'''
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / 'test_pad.c'
    path.write_text(mock + setup + reader + tests)
    binary = Path(folder) / 'test_pad'
    subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
