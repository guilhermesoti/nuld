/*
  menu.c - in-game menu for the ORBIT fork of Neutrino (phase 13): Reiniciar / Apagar / Cancelar over the paused game.

  The game's GS drawing state is write-only, so it is never touched: only image transfers. The menu is a solid panel
  rendered on the EE in the shown frame's own format and uploaded (host->local) through VIF1 DIRECT (PATH2) after
  FLUSHA, leaving the game's PATH3 mask alone (OPL unmasks it, but then reboots). The pixels under it are not saved:
  the game's next frames draw over it. Saving them took 16 KB, in ee_core (phase 13/17: its BSS then ended right under
  the stack at 0x94000) or in module storage (phase 18: USB games stopped booting on the console, #12).
*/

#include <kernel.h>
#include "eecore_config.h"
#include "ee_asm.h"
#include "igr.h"

// 1 = when no DISPFB was captured, draw into Black's frame (FBP 0, 640 wide, CT16S). Only for PCSX2, which has no
// data breakpoints: tools/build_neutrino.sh sets it with MENU_TEST=1. In a real game a guess could hit its textures
#define MENU_TEST 0

void GSM_GetDisplay(u64 out[6]); // gsm_api.c (patch_neutrino.py step 5)

#define D1_CHCR   ((vu32 *)0x10009000)
#define D1_MADR   ((vu32 *)0x10009010)
#define D1_QWC    ((vu32 *)0x10009020)
#define D2_CHCR   ((vu32 *)0x1000a000)
#define D_STAT    ((vu32 *)0x1000e010)
#define GIF_STAT  ((vu32 *)0x10003020)
#define VIF1_STAT ((vu32 *)0x10003c00)
#define CHCR_STR  0x100
#define VIF_FQC   0x1f000000
#define GIF_BUSY  0x1f000c00 // FQC and APATH

#define VIF_NOP          0
#define VIF_FLUSHA       (0x13 << 24)
#define VIF_DIRECT(n)    ((0x50 << 24) | (n))
#define GIFTAG(nloop, eop, flg, nreg) ((u64)(nloop) | (u64)(eop) << 15 | (u64)(flg) << 58 | (u64)(nreg) << 60)
#define GIF_AD    0xe
#define GS_BITBLTBUF 0x50
#define GS_TRXPOS    0x51
#define GS_TRXREG    0x52
#define GS_TRXDIR    0x53

#define PAD_START  0x0008
#define PAD_UP     0x0010
#define PAD_DOWN   0x0040
#define PAD_CIRCLE 0x2000
#define PAD_CROSS  0x4000

// 144 x 54: three items in a 6x8 font at 2x (12x16 cells), 17 px apart
#define BOX_W  144
#define BOX_H  54 // even: STRIP lines per upload
#define STRIP  2 // lines per upload
#define TEXT_X 28
#define MARK_X 10
#define ROW_Y(i) (3 + (i) * 17) // a glyph's 8th row is blank: the last row clears the border
// phase 19: the achievement notice, two rows of 5x7 ASCII at 2x: "LOGRO DESBLOQUEADO  5 PTS" and the title
#define NOTE_CHARS 31
#define NOTE_W_MAX ((20 + NOTE_CHARS * 12 + 7) & ~7) // box_w is a multiple of 8: whole qwords at 2, 3, 4 bytes a pixel
#define NOTE_TICKS (5u * 147456000u) // 2.5 s of EE clock
static u32 packet[(7 * 16 + NOTE_W_MAX * STRIP * 4) / 4] __attribute__((aligned(64)));
static u32 box_w, box_h, box_bp, box_bw, box_psm, box_x, box_y, box_bpc, box_done; // the box shown now
static int notice;
static char note_text[2][NOTE_CHARS + 1];

// 5x7 ASCII 0x20-0x5f, one byte per column, bit 0 = top row (the launcher sends titles in upper case)
static const u8 font[64][5] = {
    {0x00, 0x00, 0x00, 0x00, 0x00}, {0x00, 0x00, 0x5f, 0x00, 0x00}, {0x00, 0x07, 0x00, 0x07, 0x00}, {0x14, 0x7f, 0x14, 0x7f, 0x14}, //  !"#
    {0x24, 0x2a, 0x7f, 0x2a, 0x12}, {0x23, 0x13, 0x08, 0x64, 0x62}, {0x36, 0x49, 0x56, 0x20, 0x50}, {0x00, 0x08, 0x07, 0x03, 0x00}, // $%&'
    {0x00, 0x1c, 0x22, 0x41, 0x00}, {0x00, 0x41, 0x22, 0x1c, 0x00}, {0x2a, 0x1c, 0x7f, 0x1c, 0x2a}, {0x08, 0x08, 0x3e, 0x08, 0x08}, // ()*+
    {0x00, 0x50, 0x30, 0x00, 0x00}, {0x08, 0x08, 0x08, 0x08, 0x08}, {0x00, 0x60, 0x60, 0x00, 0x00}, {0x20, 0x10, 0x08, 0x04, 0x02}, // ,-./
    {0x3e, 0x51, 0x49, 0x45, 0x3e}, {0x00, 0x42, 0x7f, 0x40, 0x00}, {0x72, 0x49, 0x49, 0x49, 0x46}, {0x21, 0x41, 0x49, 0x4d, 0x33}, // 0123
    {0x18, 0x14, 0x12, 0x7f, 0x10}, {0x27, 0x45, 0x45, 0x45, 0x39}, {0x3c, 0x4a, 0x49, 0x49, 0x31}, {0x41, 0x21, 0x11, 0x09, 0x07}, // 4567
    {0x36, 0x49, 0x49, 0x49, 0x36}, {0x46, 0x49, 0x49, 0x29, 0x1e}, {0x00, 0x00, 0x14, 0x00, 0x00}, {0x00, 0x40, 0x34, 0x00, 0x00}, // 89:;
    {0x00, 0x08, 0x14, 0x22, 0x41}, {0x14, 0x14, 0x14, 0x14, 0x14}, {0x00, 0x41, 0x22, 0x14, 0x08}, {0x02, 0x01, 0x59, 0x09, 0x06}, // <=>?
    {0x3e, 0x41, 0x5d, 0x59, 0x4e}, {0x7c, 0x12, 0x11, 0x12, 0x7c}, {0x7f, 0x49, 0x49, 0x49, 0x36}, {0x3e, 0x41, 0x41, 0x41, 0x22}, // @ABC
    {0x7f, 0x41, 0x41, 0x41, 0x3e}, {0x7f, 0x49, 0x49, 0x49, 0x41}, {0x7f, 0x09, 0x09, 0x09, 0x01}, {0x3e, 0x41, 0x41, 0x51, 0x73}, // DEFG
    {0x7f, 0x08, 0x08, 0x08, 0x7f}, {0x00, 0x41, 0x7f, 0x41, 0x00}, {0x20, 0x40, 0x41, 0x3f, 0x01}, {0x7f, 0x08, 0x14, 0x22, 0x41}, // HIJK
    {0x7f, 0x40, 0x40, 0x40, 0x40}, {0x7f, 0x02, 0x1c, 0x02, 0x7f}, {0x7f, 0x04, 0x08, 0x10, 0x7f}, {0x3e, 0x41, 0x41, 0x41, 0x3e}, // LMNO
    {0x7f, 0x09, 0x09, 0x09, 0x06}, {0x3e, 0x41, 0x51, 0x21, 0x5e}, {0x7f, 0x09, 0x19, 0x29, 0x46}, {0x26, 0x49, 0x49, 0x49, 0x32}, // PQRS
    {0x03, 0x01, 0x7f, 0x01, 0x03}, {0x3f, 0x40, 0x40, 0x40, 0x3f}, {0x1f, 0x20, 0x40, 0x20, 0x1f}, {0x3f, 0x40, 0x38, 0x40, 0x3f}, // TUVW
    {0x63, 0x14, 0x08, 0x14, 0x63}, {0x03, 0x04, 0x78, 0x04, 0x03}, {0x61, 0x59, 0x49, 0x4d, 0x43}, {0x00, 0x7f, 0x41, 0x41, 0x41}, // XYZ[
    {0x02, 0x04, 0x08, 0x10, 0x20}, {0x00, 0x41, 0x41, 0x41, 0x7f}, {0x04, 0x02, 0x01, 0x02, 0x04}, {0x40, 0x40, 0x40, 0x40, 0x40}, // bs]^_
};

// 5x7 glyphs in 6x8 cells (the 6th column and 8th row are the gaps), bit 7 = left column
enum { G_A, G_C, G_E, G_G, G_I, G_L, G_N, G_P, G_R, G_MARK, G_S, G_T, G_O, G_W, G_F, G_SP, G_D, G_END = 0xff };
static const u8 glyph[][8] = {
    {0x70, 0x88, 0x88, 0xf8, 0x88, 0x88, 0x88, 0x00}, // A
    {0x78, 0x80, 0x80, 0x80, 0x80, 0x80, 0x78, 0x00}, // C
    {0xf8, 0x80, 0x80, 0xf0, 0x80, 0x80, 0xf8, 0x00}, // E
    {0x78, 0x80, 0x80, 0x98, 0x88, 0x88, 0x78, 0x00}, // G
    {0xf8, 0x20, 0x20, 0x20, 0x20, 0x20, 0xf8, 0x00}, // I
    {0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0xf8, 0x00}, // L
    {0x88, 0xc8, 0xa8, 0x98, 0x88, 0x88, 0x88, 0x00}, // N
    {0xf0, 0x88, 0x88, 0xf0, 0x80, 0x80, 0x80, 0x00}, // P
    {0xf0, 0x88, 0x88, 0xf0, 0xa0, 0x90, 0x88, 0x00}, // R
    {0x80, 0xc0, 0xe0, 0xf0, 0xe0, 0xc0, 0x80, 0x00}, // selection mark
    {0x78, 0x80, 0x80, 0x70, 0x08, 0x08, 0xf0, 0x00}, // S (phase 18: English labels)
    {0xf8, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x00}, // T
    {0x70, 0x88, 0x88, 0x88, 0x88, 0x88, 0x70, 0x00}, // O
    {0x88, 0x88, 0x88, 0xa8, 0xa8, 0xd8, 0x88, 0x00}, // W
    {0xf8, 0x80, 0x80, 0xf0, 0x80, 0x80, 0x80, 0x00}, // F
    {0}, // space
    {0xf0, 0x88, 0x88, 0x88, 0x88, 0x88, 0xf0, 0x00}, // D
};
enum { M_REBOOT, M_OFF, M_CANCEL, M_ITEMS };
static const u8 labels[3][M_ITEMS][10] = { // eec.IgrLang: the launcher's [ui] idioma (phase 18)
    {{G_R, G_E, G_I, G_N, G_I, G_C, G_I, G_A, G_R, G_END}, // REINICIAR
     {G_A, G_P, G_A, G_G, G_A, G_R, G_END},                // APAGAR
     {G_C, G_A, G_N, G_C, G_E, G_L, G_A, G_R, G_END}},     // CANCELAR
    {{G_R, G_E, G_S, G_T, G_A, G_R, G_T, G_END},           // RESTART
     {G_P, G_O, G_W, G_E, G_R, G_SP, G_O, G_F, G_F, G_END}, // POWER OFF
     {G_C, G_A, G_N, G_C, G_E, G_L, G_END}},               // CANCEL
    {{G_R, G_E, G_I, G_N, G_I, G_C, G_I, G_A, G_R, G_END}, // REINICIAR
     {G_D, G_E, G_S, G_L, G_I, G_G, G_A, G_R, G_END},      // DESLIGAR
     {G_C, G_A, G_N, G_C, G_E, G_L, G_A, G_R, G_END}},      // CANCELAR
};
#define label labels[eec.IgrLang < 3 ? eec.IgrLang : 0]

// NULD colours (R, G, B): panel, border (the acid accent), item, selected item
static const u8 rgb[4][3] = {{12, 14, 18}, {200, 255, 46}, {138, 145, 156}, {230, 232, 236}};
enum { C_PANEL, C_BORDER, C_ITEM, C_SEL };

// no new press for this long: resume the game (an 8BitDo adapter is not read while paused, #11)
#define IDLE_TICKS (10u * 294912000u) // COP0 Count runs at the EE clock: 10 s

static inline u32 ticks(void) { u32 t; asm volatile("mfc0 %0, $9" : "=r"(t)); return t; }

static int bpp; // bytes per pixel of the shown frame: 4 (CT32), 3 (CT24), 2 (CT16 / CT16S)
static int sel;

static int wait_clear(vu32 *reg, u32 bits) // bounded: a stuck path must not hang the pause forever
{
    int i;
    for (i = 0; i < 10000000; i++)
        if (!(*reg & bits))
            return 1;
    return 0;
}

static void vif1_send(void *p, u32 qwc)
{
    FlushCache(0);
    *D1_QWC = qwc;
    *D1_MADR = (u32)p;
    *D1_CHCR = 0x101; // from memory, normal mode, start
    asm volatile("sync.l");
    wait_clear(D1_CHCR, CHCR_STR);
}

// VIF codes + GIF A+D setup for an upload (host -> local) of data_qw qwords; returns the qwords written at p
static u32 xfer_setup(u32 *p, u64 bitbltbuf, u32 x, u32 y, u32 w, u32 h, u32 data_qw)
{
    u64 *q = (u64 *)(p + 4);
    p[0] = VIF_NOP;
    p[1] = VIF_NOP; // no MSKPATH3: the game's PATH3 mask is its own state (its GIF DMA is idle; FLUSHA waits)
    p[2] = VIF_FLUSHA;
    p[3] = VIF_DIRECT(6 + data_qw); // qwords after the DIRECT code
    q[0] = GIFTAG(4, 0, 0, 1);
    q[1] = GIF_AD;
    q[2] = bitbltbuf;
    q[3] = GS_BITBLTBUF;
    q[4] = (u64)x << 32 | (u64)y << 48; // TRXPOS: destination
    q[5] = GS_TRXPOS;
    q[6] = (u64)w | (u64)h << 32;
    q[7] = GS_TRXREG;
    q[8] = 0; // host -> local
    q[9] = GS_TRXDIR;
    q[10] = GIFTAG(data_qw, 1, 2, 0); // IMAGE
    q[11] = 0;
    return 7;
}

static int text_pixel(const u8 *s, u32 x, u32 y) // a string at 2x, (x, y) relative to its top left
{
    if (y >= 16)
        return 0;
    for (; *s != G_END; s++, x -= 12)
        if (x < 12)
            return glyph[*s][y / 2] & (0x80 >> (x / 2));
    return 0;
}

static int ascii_pixel(const char *s, u32 x, u32 y) // as text_pixel, in ASCII
{
    if (y >= 16)
        return 0;
    for (; *s; s++, x -= 12)
        if (x < 12) {
            u32 c = (u8)*s - 32, cx = x / 2, cy = y / 2;
            return c < 64 && cx < 5 && cy < 7 && (font[c][cx] >> cy & 1);
        }
    return 0;
}

static int notice_colour(u32 x, u32 y)
{
    if (x == 0 || y == 0 || x == box_w - 1 || y == box_h - 1)
        return C_BORDER;
    for (int i = 0; i < 2; i++)
        if (x >= 10 && ascii_pixel(note_text[i], x - 10, y - ROW_Y(i)))
            return i ? C_SEL : C_BORDER;
    return C_PANEL;
}

static int menu_colour(u32 x, u32 y)
{
    if (notice)
        return notice_colour(x, y);
    if (x == 0 || y == 0 || x == BOX_W - 1 || y == BOX_H - 1)
        return C_BORDER;
    for (int i = 0; i < M_ITEMS; i++) {
        u32 ty = y - ROW_Y(i);
        if (ty >= 16)
            continue;
        static const u8 mark[2] = {G_MARK, G_END};
        if (i == sel && x >= MARK_X && text_pixel(mark, x - MARK_X, ty))
            return C_SEL;
        if (x >= TEXT_X && text_pixel(label[i], x - TEXT_X, ty))
            return i == sel ? C_SEL : C_ITEM;
    }
    return C_PANEL;
}

static void render_line(u8 *d, u32 y) // box line y into d
{
    for (u32 x = 0; x < box_w; x++, d += bpp) {
        const u8 *c = rgb[menu_colour(x, y)];
        if (bpp == 2) {
            u32 p = c[0] >> 3 | (c[1] >> 3) << 5 | (c[2] >> 3) << 10 | 0x8000;
            d[0] = p, d[1] = p >> 8;
        } else {
            d[0] = c[0], d[1] = c[1], d[2] = c[2];
            if (bpp == 4)
                d[3] = 0x80;
        }
    }
}

static void vram_write(void)
{
    u32 chcr = *D1_CHCR;
    u32 line = box_w * bpp, qw = line * STRIP / 16;
    for (u32 y0 = 0; y0 < box_h; y0 += STRIP) {
        u32 n = xfer_setup(packet, (u64)box_bp << 32 | (u64)box_bw << 48 | (u64)box_psm << 56, box_x, box_y + y0,
                           box_w, STRIP, qw);
        for (u32 l = 0; l < STRIP; l++)
            render_line((u8 *)(packet + n * 4) + l * line, y0 + l);
        vif1_send(packet, n + qw);
    }
    *D1_CHCR = chcr;
    asm volatile("sync.l");
}

int Box_Drawable(void) // VBLANK handler: no transfer of the game's to the GS under way (its paths idle)
{
    return !(*D1_CHCR & CHCR_STR) && !(*D2_CHCR & CHCR_STR) && !(*VIF1_STAT & VIF_FQC) && !(*GIF_STAT & GIF_BUSY);
}

// box_w x box_h over the shown frame, centred (top: near its top). 0 when it cannot be drawn: resume at once
static int box_open(int top)
{
    u64 gs[6]; // DISPFB1, DISPFB2, PMODE, DISPLAY1, DISPLAY2, SMODE2
    GSM_GetDisplay(gs);
    int c1 = (gs[2] & 1) != 0; // circuit 1 first, as the PCRTC shows it on top
    u64 fb = c1 ? gs[0] : gs[1], disp = c1 ? gs[3] : gs[4];
#if MENU_TEST
    if (!fb)
        fb = 10 << 9 | 10 << 15;
#endif
    u32 psm = (fb >> 15) & 0x1f;
    bpp = psm == 0 ? 4 : psm == 1 ? 3 : (psm == 2 || psm == 10) ? 2 : 0;
    if (!fb || !bpp)
        return 0; // no DISPFB seen (GSM unhooked), or a format the menu cannot draw

    u32 bw = (fb >> 9) & 0x3f;
    u32 w = bw * 64, h = 224; // frame lines shown: DISPLAY height over its vertical magnification
    if (disp)
        h = (((u32)(disp >> 44) & 0x7ff) + 1) / (((u32)(disp >> 27) & 3) + 1); // u32: a u64 divide pulls 6 KB of libgcc
    if ((gs[5] & 3) == 3) // interlaced FRAME mode: the buffer holds one field, half the lines
        h /= 2;
    if (w < box_w || h < box_h) // it would spill out of the frame
        return 0;
    box_bp = (fb & 0x1ff) * 32, box_bw = bw, box_psm = psm;
    box_x = ((fb >> 32) & 0x7ff) + (w - box_w) / 2;
    box_y = ((fb >> 43) & 0x7ff) + (top && h > box_h + 32 ? 16 : (h - box_h) / 2);

    box_bpc = _ee_disable_bpc(); // our own register accesses must not trap into GSM
    wait_clear(D1_CHCR, CHCR_STR);
    wait_clear(D2_CHCR, CHCR_STR);
    // the game's own transfers are over now; a channel 1 completion it has not handled yet stays for its handler
    box_done = *D_STAT & 2;
    return 1;
}

static void box_close(void)
{
    // DMA done is not the end: the VIF1 FIFO and the GIF may still be moving our image
    wait_clear(VIF1_STAT, VIF_FQC);
    wait_clear(GIF_STAT, GIF_BUSY);
    // our VIF1 transfers flagged channel 1 done; left set, the game's VIF1 handler would run for a transfer it never
    // started. Write 1 clears it (the mask bits stay)
    if (!box_done)
        *D_STAT = 2;
    _ee_enable_bpc(box_bpc);
}

// The game is paused by the caller. Returns MENU_CANCEL, MENU_REBOOT or MENU_OFF
int Menu_Run(void)
{
    box_w = BOX_W, box_h = BOX_H;
    if (!box_open(0))
        return MENU_CANCEL;

    sel = M_CANCEL;
    vram_write();
    u16 held = IGR_Buttons(), now; // the combo is still held: only new presses count
    u32 last = ticks();
    for (;;) {
        now = IGR_Buttons();
        u16 pressed = now & ~held;
        if (now != held)
            last = ticks();
        held = now;
        if (ticks() - last > IDLE_TICKS) { // the pad says nothing (or is stuck): give the game back
            sel = M_CANCEL;
            break;
        }
        if (pressed & (PAD_UP | PAD_DOWN)) {
            sel = (sel + (pressed & PAD_UP ? M_ITEMS - 1 : 1)) % M_ITEMS;
            vram_write();
        } else if (pressed & (PAD_CIRCLE | PAD_START)) {
            sel = M_CANCEL;
            break;
        } else if (pressed & PAD_CROSS)
            break;
    }
    for (last = ticks(); IGR_Buttons() && ticks() - last < IDLE_TICKS;) // the game must not see the closing button
        ;
    box_close();
    return sel == M_REBOOT ? MENU_REBOOT : sel == M_OFF ? MENU_OFF : MENU_CANCEL;
}

static u32 put(char *d, u32 n, const char *s) // s at d[n] (bounded by note_text's rows); the new length
{
    while (*s && n < NOTE_CHARS)
        d[n++] = *s++;
    d[n] = 0;
    return n;
}

// phase 19: an unlock over the paused game for ~2.5 s, its title from the launcher's list (in module storage)
void Notice_Run(u32 id, u32 points)
{
    char num[8], *q = num + sizeof(num);
    *--q = 0;
    do
        *--q = '0' + points % 10;
    while ((points /= 10) && q > num);
    u32 n = put(note_text[0], 0, eec.IgrLang == 2 ? "CONQUISTA LIBERADA  " : eec.IgrLang == 1 ? "ACHIEVEMENT UNLOCKED  " : "LOGRO DESBLOQUEADO  ");
    n = put(note_text[0], put(note_text[0], n, q), " PTS");
    u32 m = 0;
    note_text[1][0] = 0;
    for (u32 i = 0; i < eec.RaTitleCount; i++)
        if (*(u32 *)(eec.RaTitles + i * EEC_RA_TITLE) == id)
            m = put(note_text[1], 0, (const char *)eec.RaTitles + i * EEC_RA_TITLE + 4);
    box_w = (20 + 12 * (n > m ? n : m) + 7) & ~7; // whole qwords per two lines at 2, 3 and 4 bytes a pixel
    box_h = m ? 40 : 22;                         // two rows, or the first only
    notice = 1;
    if (box_open(1)) {
        vram_write();
        for (u32 t0 = ticks(); ticks() - t0 < NOTE_TICKS;)
            ;
        box_close();
    }
    notice = 0;
}
