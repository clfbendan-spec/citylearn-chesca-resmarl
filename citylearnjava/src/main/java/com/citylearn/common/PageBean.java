package com.citylearn.common;

import java.util.List;

public class PageBean<E> {

    private List<E> rows;
    private Integer total;

    public List<E> getRows() {
        return rows;
    }

    public void setRows(List<E> rows) {
        this.rows = rows;
    }

    public Integer getTotal() {
        return total;
    }

    public void setTotal(Integer total) {
        this.total = total;
    }
}
