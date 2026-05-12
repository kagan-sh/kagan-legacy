export interface Attachment {
  id: string;
  type: string;
  name: string;
  /** MIME type — required for image attachments so the server can build the
   * multimodal content block. For non-image attachments this is optional. */
  mimeType?: string;
  content?: string;
  file?: File;
}

/** Maximum total size (bytes) for a single image attachment sent as a data URL. */
export const IMAGE_ATTACHMENT_MAX_BYTES = 4 * 1024 * 1024; // 4 MB

/** Maximum number of attachments per message. */
export const ATTACHMENT_MAX_COUNT = 3;
