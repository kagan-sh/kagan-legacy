export interface Attachment {
  id: string;
  type: string;
  name: string;
  content?: string;
  file?: File;
}
