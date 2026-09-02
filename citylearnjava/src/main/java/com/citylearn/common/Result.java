package com.citylearn.common;

import java.util.ArrayList;

public class Result<E> {
    private E data;
    private Integer code=0;
    private String message;

    public E getData() {
        return data;
    }

    public void setData(E data) {
        this.data = data;
    }

    public Integer getCode() {
        return code;
    }

    public void setCode(Integer code) {
        this.code = code;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public  static <E> Result<E> success(E data){
        Result<E> result=new Result<>();
        result.setData(data);
        result.setMessage("成功");
        return result;
    }

    public  static <E> Result<E> success(){
        Result<E> result=new Result<>();
        result.setMessage("成功");
        return result;
    }

    public  static <E> Result<E> fail(Integer code){
        Result<E> result=new Result<>();
        result.setCode(code);
        result.setMessage("失败");
        return result;
    }

    public  static <E> Result<E> fail(){
        Result<E> result=new Result<>();
        result.setCode(500);
        result.setMessage("失败");
        return result;
    }

    public  static <E> Result<E> fail(String message){
        Result<E> result=new Result<>();
        result.setCode(500);
        result.setMessage(message);
        return result;
    }
}
