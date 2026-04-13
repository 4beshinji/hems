/**
 * Avatar type resolution — reads VITE_AVATAR_TYPE at build time.
 * Defaults to 'psd' (2D 立ち絵) when unset; set VITE_AVATAR_TYPE=vrm to opt into 3D.
 */
const RAW = (import.meta.env.VITE_AVATAR_TYPE as string | undefined) ?? 'psd'

export const AVATAR_TYPE: 'psd' | 'vrm' = RAW === 'vrm' ? 'vrm' : 'psd'

export const IS_PSD = AVATAR_TYPE === 'psd'
