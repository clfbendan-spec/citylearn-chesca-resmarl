package com.citylearn.config;

import org.springframework.beans.factory.annotation.Value;

import java.time.ZoneId;
import java.util.*;

/**
 * @author chenglifu
 */
public interface SystemConfig {

    default String getUUID(){
        return UUID.randomUUID().toString().replace("-","");
    }

    Integer SIZE_KB=1024;

    default Date endOfDay(Date date){
        if(null==date){
            return null;
        }
        Calendar temp=Calendar.getInstance();
        temp.setTime(date);
        temp.set(Calendar.HOUR_OF_DAY,23);
        temp.set(Calendar.MINUTE,59);
        temp.set(Calendar.SECOND,59);
        return temp.getTime();
    }
    default Date beginOfDay(Date date){
        if(null==date){
            return null;
        }
        Calendar temp=Calendar.getInstance();
        temp.setTime(date);
        temp.set(Calendar.HOUR_OF_DAY,0);
        temp.set(Calendar.MINUTE,0);
        temp.set(Calendar.SECOND,0);
        return temp.getTime();
    }
    default Date timeZero(){
        Date date=new Date();
        date.setTime(0L);
        return date;
    }
    default Date nextDay(Date date){
        if(null==date){
            return null;
        }
        return Date.from(date.toInstant().atZone(ZoneId.systemDefault()).toLocalDateTime().plusSeconds(1L).atZone(ZoneId.systemDefault()).toInstant());
    }

}
