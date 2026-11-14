package com.citylearn.building;

import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.nio.file.*;
import java.util.Comparator;

final class DatasetSnapshotFiles {
    private DatasetSnapshotFiles() {}
    static void cleanupOnRollback(Path directory) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCompletion(int status) {
                if(status==STATUS_COMMITTED) return;
                try(java.util.stream.Stream<Path> paths=Files.walk(directory)) {
                    for(Path path:(Iterable<Path>)paths.sorted(Comparator.reverseOrder())::iterator) Files.deleteIfExists(path);
                } catch(Exception error) {java.util.logging.Logger.getLogger(DatasetSnapshotFiles.class.getName()).warning("Cannot clean rolled-back snapshot: "+directory);}
            }
        });
    }
}
