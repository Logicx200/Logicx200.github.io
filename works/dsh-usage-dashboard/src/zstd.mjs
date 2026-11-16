/**
 * Concatenated-frame Zstandard reader for DSH session artifacts.
 *
 * A `session.v<N>.jsonl.zstd` artifact is a container of independently
 * decodable, checksummed Zstandard frames, each holding one batch of JSONL
 * lines. The container is the same across log format versions — only the record
 * shapes inside moved between v3 and v4 — so this reader serves either.
 * Node's one-shot `zstdDecompressSync` stops after the first frame, so
 * the frames are located structurally first and decoded one by one — the same
 * approach `@deepseek-ai/dsh-session-persistence-jsonl` uses, re-derived here
 * so this plugin depends on no private package internals.
 *
 * @module dsh-usage-dashboard/zstd
 */

import { zstdDecompressSync } from 'node:zlib'

/** Little-endian byte count of the Zstandard frame magic `0xFD2FB528`. */
const ZSTD_MAGIC = 0xfd2fb528

/** One structurally complete frame's byte range inside the artifact. */
/**
 * @typedef {{ start: number, end: number }} FrameRange
 */

/**
 * Locate every structurally complete Zstandard frame without decoding blocks.
 *
 * The frame header, each block header, and the optional trailing checksum
 * carry their own lengths, so a pure structural walk finds frame boundaries
 * without decompressing anything.
 *
 * @param {Buffer} buffer - the complete artifact bytes.
 * @returns {{ frames: FrameRange[], tornStart: number | undefined }} complete
 *   frames in file order plus the start of an incomplete final frame.
 * @throws {Error} when the container is structurally invalid.
 */
export function scanZstdFrames(buffer) {
  /** @type {FrameRange[]} */
  const frames = []
  let offset = 0
  while (offset < buffer.length) {
    const start = offset
    if (buffer.length - offset < 4) return { frames, tornStart: start }
    if (buffer.readUInt32LE(offset) !== ZSTD_MAGIC) {
      throw new Error(`corrupt Zstandard session log: invalid frame magic at byte ${offset}`)
    }
    offset += 4
    if (offset === buffer.length) return { frames, tornStart: start }
    const descriptor = buffer.readUInt8(offset)
    offset += 1
    if ((descriptor & 0x18) !== 0) {
      throw new Error(`corrupt Zstandard session log: reserved frame-header bit at byte ${offset - 1}`)
    }
    const contentSizeFlag = descriptor >>> 6
    const singleSegment = (descriptor & 0x20) !== 0
    const checksum = (descriptor & 0x04) !== 0
    const dictionaryFlag = descriptor & 0x03
    const dictionaryBytes = dictionaryFlag === 3 ? 4 : dictionaryFlag
    const contentSizeBytes =
      contentSizeFlag === 0 ? (singleSegment ? 1 : 0) : 1 << contentSizeFlag
    const remainingHeaderBytes = (singleSegment ? 0 : 1) + dictionaryBytes + contentSizeBytes
    if (buffer.length - offset < remainingHeaderBytes) return { frames, tornStart: start }
    offset += remainingHeaderBytes
    for (;;) {
      if (buffer.length - offset < 3) return { frames, tornStart: start }
      const blockHeader = buffer.readUIntLE(offset, 3)
      offset += 3
      const lastBlock = (blockHeader & 1) !== 0
      const blockType = (blockHeader >>> 1) & 3
      const blockSize = blockHeader >>> 3
      if (blockType === 3) {
        throw new Error(`corrupt Zstandard session log: reserved block type at byte ${offset - 3}`)
      }
      const payloadBytes = blockType === 1 ? 1 : blockSize
      if (buffer.length - offset < payloadBytes) return { frames, tornStart: start }
      offset += payloadBytes
      if (lastBlock) break
    }
    if (checksum) {
      if (buffer.length - offset < 4) return { frames, tornStart: start }
      offset += 4
    }
    frames.push({ start, end: offset })
  }
  return { frames }
}

/**
 * Decode every complete frame of one artifact into JSONL lines.
 *
 * A torn trailing frame — the artifact is rewritten on every batch, so a read
 * can catch a partially flushed one — contributes the plaintext that is
 * already durable: a frame with an unfinished block simply yields nothing.
 * Every malformed *complete* frame is a real corruption and throws.
 *
 * @param {Buffer} buffer - the complete artifact bytes.
 * @returns {string[]} JSONL lines in durable order, without empty entries.
 * @throws {Error} when the container or a complete frame is corrupt.
 */
export function readZstdJsonlLines(buffer) {
  const { frames } = scanZstdFrames(buffer)
  /** @type {string[]} */
  const lines = []
  for (const frame of frames) {
    const plain = zstdDecompressSync(buffer.subarray(frame.start, frame.end))
    for (const line of plain.toString('utf8').split('\n')) {
      if (line.length > 0) lines.push(line)
    }
  }
  return lines
}
