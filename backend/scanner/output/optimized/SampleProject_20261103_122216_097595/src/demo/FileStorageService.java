package demo;

import java.io.FileInputStream;
import java.io.IOException;

/**
 * Resource-leak sample: stream opened without try-with-resources / close.
 */
public class FileStorageService {

    public byte[] readFileData(String path) throws IOException {
        FileInputStream fis = new FileInputStream(path);
        byte[] buffer = new byte[1024];
        int read = fis.read(buffer);
        if (read <= 0) {
            return new byte[0];
        }
        byte[] result = new byte[read];
        System.arraycopy(buffer, 0, result, 0, read);
        return result;
    }
}
