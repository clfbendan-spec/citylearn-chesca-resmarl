package com.citylearn.service;

import com.citylearn.dao.PyFileMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Transactional
class PyFileVisibilityTest {
    @Autowired JdbcTemplate jdbc;
    @Autowired PyFileMapper files;
    @Autowired PyFileService service;

    @Test void hiddenScriptsAreExcludedFromAllAndTypeFilteredListsWithoutDeletingMetadata() {
        String owner = UUID.randomUUID().toString();
        String shown = UUID.randomUUID().toString();
        String hidden = UUID.randomUUID().toString();
        String unset = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO py_file(id,file_name,create_user,if_system,if_show,script_type) VALUES (?,'shown.py',?,0,1,'eval')", shown, owner);
        jdbc.update("INSERT INTO py_file(id,file_name,create_user,if_system,if_show,script_type) VALUES (?,'hidden.py',?,0,0,'both')", hidden, owner);
        jdbc.update("INSERT INTO py_file(id,file_name,create_user,if_system,if_show,script_type) VALUES (?,'unset.py',?,0,NULL,'train')", unset, owner);
        Set<String> all = service.getPyFileList(owner, null).stream()
                .map(file -> file.getId()).collect(Collectors.toSet());
        assertTrue(all.contains(shown));
        assertTrue(all.contains(unset), "Legacy unset visibility remains visible");
        assertFalse(all.contains(hidden));
        assertFalse(service.getPyFileList(owner, "both").stream()
                .anyMatch(file -> hidden.equals(file.getId())));
        assertNotNull(files.selectById(hidden), "Hiding must preserve script metadata");
    }
}
