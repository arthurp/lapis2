ava_name("Intel(R) Movidius(TM) Neural Compute SDK");
ava_version("2.08.01");
ava_identifier(MVNC);
ava_number(1);
//ava_cflags(-DAVA_RECORD_REPLAY);
ava_libs(-lmvnc);
ava_export_qualifier(dllexport);

ava_storage_resource memory;
ava_throughput_resource calls;

struct metadata {
    unsigned long int size;
};
ava_register_metadata(struct metadata);

#include <mvnc.h>
