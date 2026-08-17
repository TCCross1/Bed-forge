/** No-op Workbox stand-in. BedForge uses IndexedDB offline queue, not a service worker. */
class WorkboxNoop {
  apply() {}
}

module.exports = {
  InjectManifest: WorkboxNoop,
  GenerateSW: WorkboxNoop,
};
