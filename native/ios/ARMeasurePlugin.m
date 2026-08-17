#import <Capacitor/Capacitor.h>

CAP_PLUGIN(ARMeasurePlugin, "ARMeasure",
    CAP_PLUGIN_METHOD(capabilities, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(setTorch, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(present, CAPPluginReturnPromise);
)
