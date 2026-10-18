return {
    LrSdkVersion = 7.4,
    LrSdkMinimumVersion = 7.4,
    LrToolkitIdentifier = 'local.lightroom.local-develop',
    LrPluginName = '本地 AI 顯影',
    VERSION = { major=1, minor=13, revision=1, build=1 },
    LrLibraryMenuItems = {
        { title='本地分析並套用選取照片（全部）', file='Auto.lua' },
        { title='本地分析並套用選取照片（僅未修改）', file='AutoUnmodified.lua' },
        { title='匯出選取照片供分析（手動）', file='Export.lua' },
        { title='將修圖計畫套用至選取照片（手動）', file='Apply.lua' },
    },
}
