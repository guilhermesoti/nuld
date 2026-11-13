/* AFL-3.0: freestanding compatibility for current PS2SDK's SifLoadElfPart.
 * ee_core links without libc; newer libkernel versions call strlcpy.
 */
#include <stddef.h>
size_t strlcpy(char *dst, const char *src, size_t size)
{
    size_t len = 0;
    while (src[len]) len++;
    if (size) {
        size_t n = len < size - 1 ? len : size - 1;
        for (size_t i = 0; i < n; i++) dst[i] = src[i];
        dst[n] = '\0';
    }
    return len;
}
