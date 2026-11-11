package demo;

import java.util.HashMap;
import java.util.Map;

/**
 * Mutable static shared state without synchronization.
 */
public class GlobalConfig {

    public static Map<String, String> cacheMap = new HashMap<>();

    public void updateCache(String key, String value) {
        cacheMap.put(key, value);
    }
}
