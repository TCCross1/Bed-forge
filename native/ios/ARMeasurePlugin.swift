import Foundation
import Capacitor
import ARKit
import AVFoundation
import UIKit
import CoreMotion

@objc(ARMeasurePlugin)
public class ARMeasurePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "ARMeasurePlugin"
    public let jsName = "ARMeasure"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "capabilities", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "setTorch", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "present", returnType: CAPPluginReturnPromise)
    ]

    private var presented: ARMeasureViewController?
    private var pendingCall: CAPPluginCall?

    @objc func capabilities(_ call: CAPPluginCall) {
        let lidar = ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh)
        let arkit = ARWorldTrackingConfiguration.isSupported
        call.resolve([
            "arkit": arkit,
            "lidar": lidar,
            "torch": AVCaptureDevice.default(for: .video)?.hasTorch ?? false,
            "engine": lidar ? "arkit-lidar" : (arkit ? "arkit" : "none"),
            "honesty_label": lidar ? "ARKit with LiDAR" : (arkit ? "ARKit world tracking (no LiDAR)" : "ARKit not supported"),
            "web_is_arkit": false
        ])
    }

    @objc func setTorch(_ call: CAPPluginCall) {
        let on = call.getBool("on") ?? false
        ARMeasureViewController.setTorch(on)
        call.resolve(["on": on])
    }

    @objc func present(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard ARWorldTrackingConfiguration.isSupported else {
                call.reject("ARKit is not supported on this device")
                return
            }
            let vc = ARMeasureViewController()
            vc.modalPresentationStyle = .fullScreen
            vc.onComplete = { [weak self] result in
                self?.pendingCall?.resolve(result)
                self?.pendingCall = nil
                self?.presented = nil
            }
            vc.onCancel = { [weak self] in
                self?.pendingCall?.reject("cancelled")
                self?.pendingCall = nil
                self?.presented = nil
            }
            self.presented = vc
            self.pendingCall = call
            self.bridge?.viewController?.present(vc, animated: true)
        }
    }
}
