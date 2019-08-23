#include <zlib.h>

int main() {
  z_stream defstream = {};
  deflateInit(&defstream, Z_BEST_COMPRESSION);

  return 0;
}
